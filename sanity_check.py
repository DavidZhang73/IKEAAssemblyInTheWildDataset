import json
import os
import re
import requests
import jsonschema

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


def json_schema_check(dataset):
    with open(SCHEMA_PATHNAME, "r", encoding="utf8") as sf:
        schema = json.load(sf)
    error_video_list = set()
    for error in jsonschema.Draft202012Validator(schema).iter_errors(dataset):
        print(f"[{error.json_path}]", error.message)
        for result in VIDEO_ERROR_REG.findall(error.json_path):
            error_video_list.add((int(result[0]), int(result[1])))
    if error_video_list:
        get_video_related_error_info(dataset, error_video_list)


def check_url(url, message, youtube=False):
    if youtube:
        r = requests.head("https://www.youtube.com/oembed?url=" + url)
        if r.status_code != 200 and r.status_code != 401:
            return message.format(url=url) + f" (status code: {r.status_code}){os.linesep}"
    else:
        r = requests.head(url)
        if r.status_code != 200:
            return message.format(url=url) + f" (status code: {r.status_code}){os.linesep}"
    return ""


def url_availability_check(dataset):
    def _url_availability_check(d):
        info = dict(id=d["id"], name=d["name"], subCategory=d["subCategory"], typeName=d["typeName"])
        main_image_url = d["mainImageUrl"]
        manual_pdf_url_list = [manual["url"] for manual in d["manualList"]]
        video_url_list = [video["url"] for video in d["videoList"]]

        fail_message = ""

        fail_message += check_url(main_image_url, "Error: Main Image URL {url}")
        for i, manual_pdf_url in enumerate(manual_pdf_url_list):
            fail_message += check_url(manual_pdf_url, f"Error: Manual PDF {i} URL {{url}}")
        for i, video_url in enumerate(video_url_list):
            fail_message += check_url(video_url, f"Error: Video {i} URL {{url}}", youtube=True)
        if fail_message:
            print(f"Error: Furniture {info}")
            print(fail_message)

    from tqdm.contrib.concurrent import thread_map

    thread_map(_url_availability_check, dataset, max_workers=8)


if __name__ == "__main__":
    with open(DATASET_PATHNAME, "r", encoding="utf8") as df:
        dataset = json.load(df)
    json_schema_check(dataset)
    url_availability_check(dataset)
