import os
import json
import pathlib
import argparse
import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image

import tensorflow as tf

from waymo_open_dataset import dataset_pb2 as open_dataset

tf.compat.v1.enable_eager_execution()


class WaymoCOCOConverter():
    def __init__(self,
                 image_dir,
                 image_prefix=None,
                 write_image=True,
                 add_waymo_info=False,
                 add_coco_info=True,
                 frame_index_ones_place=None):
        """
        Parameters
        ----------
        add_waymo_info : bool
            include additional information out of original COCO format.
        add_coco_info : bool
            include information in original COCO format,
            but out of Waymo Open Dataset.
            if set to False, COCO compatibility breaks.
        frame_index_ones_place : int
            extract 1/10 size dataset based on ones place of frame index.
        """

        self.image_dir = image_dir
        self.image_prefix = image_prefix
        self.write_image = write_image
        self.add_waymo_info = add_waymo_info
        self.add_coco_info = add_coco_info
        if frame_index_ones_place is not None:
            self.frame_index_ones_place = int(frame_index_ones_place)
            assert 0 <= self.frame_index_ones_place < 10
        else:
            self.frame_index_ones_place = None

        self.init_waymo_dataset_proto_info()
        self.init_coco_format_info()

        self.img_index = 0
        self.annotation_index = 0
        self.img_dicts = []
        self.annotation_dicts = []

    def init_waymo_dataset_proto_info(self):
        # these lists should correspond to label.proto and dataset.proto in
        # https://github.com/waymo-research/waymo-open-dataset/
        self.waymo_class_mapping = [
            'TYPE_UNKNOWN', 'TYPE_VEHICLE', 'TYPE_PEDESTRIAN', 'TYPE_SIGN',
            'TYPE_CYCLIST'
        ]
        self.waymo_camera_names = {
            0: 'UNKNOWN',
            1: 'FRONT',
            2: 'FRONT_LEFT',
            3: 'FRONT_RIGHT',
            4: 'SIDE_LEFT',
            5: 'SIDE_RIGHT',
        }

    def init_coco_format_info(self):
        self.dataset_info = {
            "year": 2022,
            "version": "v1.3.1_20220422",
            "description": "Waymo Open Dataset 2D Detection",
            "contributor": "Waymo LLC",
            "url": "https://waymo.com/open/",
            "date_created": datetime.datetime.utcnow().isoformat(' '),
        }
        self.licenses = [{
            "id": 1,
            "name": "Waymo Dataset License Agreement for Non-Commercial Use",
            "url": "https://waymo.com/open/terms/",
        }]
        # Waymo Open Dataset categories for "ALL_NS" setting
        # (all Object Types except signs)
        # Note that ids are different from those of waymo_class_mapping
        self.target_categories = [
            {
                "id": 1,
                "name": "TYPE_PEDESTRIAN",
                "supercategory": "person",
            },
            {
                "id": 2,
                "name": "TYPE_CYCLIST",
                "supercategory": "bike_plus",
            },
            {
                "id": 3,
                "name": "TYPE_VEHICLE",
                "supercategory": "vehicle",
            }
            # {
            #     "id" : 13,
            #     "name" : "TYPE_SIGN",
            #     "supercategory" : "outdoor",
            # }
            # {
            #     "id" : ,
            #     "name" : "TYPE_UNKNOWN",
            #     "supercategory" : "unknown",
            # },
        ]

    def process_sequences(self, tfrecord_paths):
        if not isinstance(tfrecord_paths, (list, tuple)):
            tfrecord_paths = [tfrecord_paths]

        # loop for tfrecord sequences
        for tfrecord_index, tfrecord_path in enumerate(sorted(tfrecord_paths)):
            sequence_data = tf.data.TFRecordDataset(str(tfrecord_path),
                                                    compression_type='')
            # loop for frames in each sequence
            for frame_index, frame_data in enumerate(sequence_data):
                if self.frame_index_ones_place is not None:
                    if frame_index % 10 != self.frame_index_ones_place:
                        continue
                frame = open_dataset.Frame()
                frame.ParseFromString(bytearray(frame_data.numpy()))
                self.process_frame(frame, frame_index, tfrecord_index)

    def process_frame(self, frame, frame_index, tfrecord_index):
        #print(f'frame: {frame_index}, {len(frame.images)} cameras')

        # loop for camera images in each frame
        for camera_image in frame.images:
            if camera_image.name !=1:
                break
            self.process_img(camera_image, frame, frame_index, tfrecord_index)
            #print(frame.camera_labels)
            img = tf.image.decode_jpeg(camera_image.image).numpy()[:, :, ::-1]
            img_height = img.shape[0]
            img_width = img.shape[1]
            img_size = img_height * img_width
            for camera_label in frame.camera_labels:
                # Ignore camera labels that do not correspond to this camera.
                if camera_label.name != camera_image.name:
                    continue
                self.add_coco_annotation_dict(camera_label, img_size)
            # increment img_index after adding annotations
            self.img_index += 1

    def process_img(self, camera_image, frame, frame_index, tfrecord_index):
        img_filename = f'{tfrecord_index:05d}_{frame_index:05d}_camera{camera_image.name}.jpg'  # noqa
        # imgbox_filename = f'{tfrecord_index:05d}_{frame_index:05d}_camera{camera_image.name}_waymo_boxes.jpg'
        # img_filename = f'{frame.context.name}_{camera_image.name}_{frame.timestamp_micros}.jpg'  # noqa
        if self.image_prefix is not None:
            img_filename = self.image_prefix + '_' + img_filename
        img_path = os.path.join(self.image_dir, img_filename)
        img = tf.image.decode_jpeg(camera_image.image).numpy()[:, :, ::-1]
        img_height = img.shape[0]
        img_width = img.shape[1]
        img_size = img_height*img_width
        if self.write_image:
            with open(img_path, 'wb') as f:
                f.write(bytearray(camera_image.image))
        # Draw the camera labels.
        # for camera_labels in frame.camera_labels:
        #     # Ignore camera labels that do not correspond to this camera.
        #     ax = plt.subplot()
        #     ax.clear()
        #     if camera_labels.name != camera_image.name:
        #         continue
        #
        #     # Iterate over the individual labels.
        #     else:
        #         for label in camera_labels.labels:
        #         # Draw the object bounding box.
        #             if label.box.length*label.box.width<0.001*img_size:
        #                 continue
        #             ax.add_patch(patches.Rectangle(
        #                xy=(label.box.center_x - 0.5 * label.box.length,
        #                    label.box.center_y - 0.5 * label.box.width),
        #                width=label.box.length,
        #                height=label.box.width,
        #                linewidth=1,
        #                edgecolor='red',
        #                facecolor='none'))

            # Show the camera image.
            # plt.imshow(tf.image.decode_jpeg(camera_image.image))
            # plt.title(open_dataset.CameraName.Name.Name(camera_image.name))
            # plt.grid(False)
            # plt.axis('off')
            # img_path2 = os.path.join(self.image_dir, 'waymo_boxes', imgbox_filename)
            # plt.savefig(img_path2)

        self.add_coco_img_dict(img_filename,
                               height=img_height,
                               width=img_width,
                               sequence_id=tfrecord_index,
                               frame_id=frame_index,
                               camera_id=int(camera_image.name),
                               frame=frame)

    def add_coco_img_dict(self,
                          file_name,
                          height=None,
                          width=None,
                          sequence_id=None,
                          frame_id=None,
                          camera_id=None,
                          frame=None):
        if height is None or width is None:
            raise ValueError
        img_dict = {
            "id": self.img_index,
            "width": width,
            "height": height,
            "file_name": file_name,
            "license": 1,
        }
        if self.add_coco_info:
            img_dict["flickr_url"] = ""
            img_dict["coco_url"] = ""
            img_dict["date_captured"] = ""
        if self.add_waymo_info:
            img_dict["context_name"] = frame.context.name
            img_dict["timestamp_micros"] = frame.timestamp_micros
            img_dict["camera_id"] = camera_id
            img_dict["sequence_id"] = sequence_id
            img_dict["frame_id"] = frame_id
            img_dict["time_of_day"] = frame.context.stats.time_of_day
            img_dict["location"] = frame.context.stats.location
            img_dict["weather"] = frame.context.stats.weather

        self.img_dicts.append(img_dict)

    def add_coco_annotation_dict(self, camera_label, img_size):
        annotation_dicts = []
        for box_label in camera_label.labels:
 #           print(box_label)
            category_name_to_id = {
                category['name']: category['id']
                for category in self.target_categories
            }
            category_name = self.waymo_class_mapping[box_label.type]
            if category_name not in category_name_to_id:
                continue
            category_id = category_name_to_id[category_name]
            width = box_label.box.length  # box.length: dim x
            height = box_label.box.width  # box.width: dim y
            x1 = box_label.box.center_x - width / 2
            y1 = box_label.box.center_y - height / 2

            annotation_dict = {
                "id": self.annotation_index,
                "image_id": self.img_index,
                "category_id": category_id,
                "segmentation": None,
                "area": width * height,
                "bbox": [x1, y1, width, height],
                "iscrowd": 0,
            }
            if self.add_waymo_info:
                annotation_dict["track_id"] = box_label.id
                annotation_dict["det_difficult"] = \
                    box_label.detection_difficulty_level
                annotation_dict["track_difficult"] = \
                    box_label.tracking_difficulty_level
            if annotation_dict["area"] <0.005*img_size:
                continue
            annotation_dicts.append(annotation_dict)
            self.annotation_index += 1
        self.annotation_dicts.extend(annotation_dicts)

    def write_coco(self, label_path, json_indent=None):
        output_dict = {
            "info": self.dataset_info,
            "licenses": self.licenses,
            "categories": self.target_categories,
            "images": self.img_dicts,
        }
        if self.annotation_dicts:
            output_dict["annotations"] = self.annotation_dicts
        if self.add_waymo_info:
            output_dict["camera_names"] = self.waymo_camera_names

        with open(label_path, mode='w') as f:
            # dump with a trick for rounding float
            json.dump(json.loads(json.dumps(output_dict),
                                 parse_float=lambda x: round(float(x), 6)),
                      f,
                      indent=json_indent,
                      sort_keys=False)
        return output_dict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tfrecord_dir', required=True, type=str)
    parser.add_argument('--work_dir', default='.', type=str)
    parser.add_argument('--image_dirname', required=True, type=str)
    parser.add_argument('--image_filename_prefix', default=None, type=str)
    parser.add_argument('--skip_write_image', action='store_true')
    parser.add_argument('--label_dirname', default='annotations', type=str)
    parser.add_argument('--label_filename', required=True, type=str)
    parser.add_argument('--json_indent', default=None, type=int)
    parser.add_argument('--add_waymo_info', action='store_true')
    parser.add_argument(
        '--frame_index_ones_place',
        default=None,
        type=int,
        help='extract 1/10 size dataset based on ones place of frame index.')
    parser.add_argument('--sequence_limit',
                        default=None,
                        type=int,
                        help='limit number of sequences. useful for debug.')
    args = parser.parse_args()

    image_dir = os.path.join(args.work_dir, args.image_dirname)
    label_dir = os.path.join(args.work_dir, args.label_dirname)
    os.makedirs(image_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)
    label_path = os.path.join(label_dir, args.label_filename)

    tfrecord_list = list(
        sorted(pathlib.Path(args.tfrecord_dir).glob('*.tfrecord')))
    if args.sequence_limit is not None:
        tfrecord_list = tfrecord_list[:args.sequence_limit]

    waymo_converter = WaymoCOCOConverter(
        image_dir,
        image_prefix=args.image_filename_prefix,
        write_image=(not args.skip_write_image),
        add_waymo_info=args.add_waymo_info,
        frame_index_ones_place=args.frame_index_ones_place)
    waymo_converter.process_sequences(tfrecord_list)
    out_dict = waymo_converter.write_coco(label_path, json_indent=args.json_indent)
    # print(f'Output dictionary: {out_dict}')
    # f = open(label_path)
    # out_dict = json.load(f)
    # annot = out_dict['annotations']
    # ims = out_dict['images']
    # path = os.path.join(image_dir, 'coco_boxes')
    # os.makedirs(path)
    # for j in ims:
    #     img_path1 = os.path.join(image_dir, j['file_name'])
    #     img = Image.open(img_path1)
    #     ax = plt.gca()
    #     ax.clear()
    #     plt.imshow(img)
    #     n = j['id']
    #     for i in annot:
    #         if i['image_id'] == n:
    #             x1 = i['bbox'][0]
    #             y1 = i['bbox'][1]
    #             w = i['bbox'][2]
    #             h = i['bbox'][3]
    #             rect = patches.Rectangle((x1, y1), w, h, linewidth=1, edgecolor='r', facecolor='none')
    #             ax.add_patch(rect)
    #         else:
    #             continue
    #     img_path2 = os.path.join(path, j['file_name'])
    #     plt.savefig(img_path2)
    # f.close()



if __name__ == "__main__":
    main()
