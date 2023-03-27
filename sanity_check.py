import json
import jsonschema
import re

DATASET_PATHNAME = r"dataset/IKEAAssemblyInTheWildDataset.json"
# DATASET_PATHNAME = r"dataset/split/train.json"
# DATASET_PATHNAME = r"dataset/split/val.json"
# DATASET_PATHNAME = r"dataset/split/test.json"
SCHEMA_PATHNAME = r"dataset_schema.json"
VIDEO_ERROR_REG = re.compile(r"\$\[(\d+)\].videoList\[(\d+)\]")


def get_video_related_error_info(dataset, error_video_list):
    print("Video Errors:")
    for data_index, video_index in error_video_list:
        data = dataset[data_index]
        video = data["videoList"][video_index]
        video_path = f"'{data['subCategory']}/{data['id']}/video/{video['url'].split('v=')[-1]}.mp4'"
        print(video_path, video["url"])


def main():
    with open(DATASET_PATHNAME, "r", encoding="utf8") as df, open(SCHEMA_PATHNAME, "r", encoding="utf8") as sf:
        dataset = json.load(df)
        schema = json.load(sf)
    error_video_list = set()
    for error in jsonschema.Draft202012Validator(schema).iter_errors(dataset):
        print(f"[{error.json_path}]", error.message)
        for result in VIDEO_ERROR_REG.findall(error.json_path):
            error_video_list.add((int(result[0]), int(result[1])))
    if error_video_list:
        get_video_related_error_info(dataset, error_video_list)


if __name__ == "__main__":
    main()
