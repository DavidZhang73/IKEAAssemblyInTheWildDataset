import json
import os
import traceback
from time import sleep, time
import logging

import fitz
import requests
import yt_dlp
from PIL import Image
from tqdm.contrib.concurrent import thread_map

from queue import Queue

# Configuration
DATASET_PATH = os.path.join(".", "dataset")
DATASET_JSON_NAME = "IKEAAssemblyInTheWildDataset.json"
DATASET_JSON_PATHNAME = os.path.join(DATASET_PATH, DATASET_JSON_NAME)
LOG_LEVEL = logging.DEBUG
LOG_PATHNAME = os.path.join(DATASET_PATH, f"{time()}.log")
USE_CACHE = True
YT_DLP_OPTION = {
    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    # 'format': 'worst[ext=mp4]+worst[ext=m4a]/worst[ext=mp4]/worst',
    "quiet": True,
    "restrictfilenames": True,
    "noprogress": True,
}

# Logging
logging.basicConfig(
    level=LOG_LEVEL,
    filename=LOG_PATHNAME,
    filemode="w",
    datefmt="%Y-%m-%d %H:%M:%S",
    format="%(asctime)s [%(processName)s(%(process)d)] [%(threadName)s(%(thread)d)] "
    "[%(funcName)s(%(lineno)d)] [%(levelname)s]: %(message)s",
)
logger = logging.getLogger()


# Retry decorator
def retry(times):
    def decorator(func):
        def inner(*args, **kwargs):
            attempt = 0
            while attempt < times:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"{e}, waiting for retry, {times - attempt} times remains")
                    attempt += 1
                    sleep(0.1 * attempt)
            return func(*args, **kwargs)

        return inner

    return decorator


# Internal functions
@retry(5)
def _get_response(url, stream=False):
    return requests.get(url, stream=stream)


def _get_binary(url, output_path, output_name):
    os.makedirs(output_path, exist_ok=True)
    output_pathname = os.path.abspath(os.path.join(output_path, output_name))
    if os.path.exists(output_pathname) and USE_CACHE:
        logger.info(f"{output_pathname} exists, skip")
        return output_pathname
    r = _get_response(url, stream=True)
    output_pathname_part = output_pathname + ".part"
    with open(output_pathname_part, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    os.rename(output_pathname_part, output_pathname)
    return output_pathname


@retry(5)
def _get_video(url, output_path):
    os.makedirs(output_path, exist_ok=True)
    option = YT_DLP_OPTION.copy()
    option["outtmpl"] = os.path.join(os.path.abspath(output_path), "%(id)s.%(ext)s")
    video_id = url.split("watch?v=")[-1]
    output_pathname = os.path.join(os.path.abspath(output_path), f"{video_id}.mp4")
    if os.path.exists(output_pathname) and USE_CACHE:
        logger.info(f"{output_pathname} exists, skip")
    else:
        with yt_dlp.YoutubeDL(option) as ydl:
            ydl.download([url])
    return output_pathname


def _get_output_name(url):
    return url.split("/")[-1]


def _get_output_path(item):
    return os.path.join(DATASET_PATH, item["category"], item["subCategory"], item["id"])


# Main functions
def get_image(item, output_path):
    logger.debug(f'Start to get image for {item["id"]}')
    url = item["mainImageUrl"]
    if url:
        _get_binary(url, output_path, _get_output_name(url))
    logger.debug(f'Finish to get image for {item["id"]}')


def get_manual(item, output_path):
    logger.debug(f'Start to get manual for {item["id"]}')
    manual_pix_list = []
    for i, manual in enumerate(item["manualList"]):
        url = manual["url"]
        if url:
            pathname = _get_binary(url, os.path.join(output_path, "manual"), _get_output_name(url))
            # pageList
            page_output_path = os.path.join(output_path, "manual", str(i + 1))
            os.makedirs(page_output_path, exist_ok=True)
            with fitz.open(pathname) as doc:
                pix_list = []
                for index, page in enumerate(doc):
                    pix = page.get_pixmap(dpi=150)
                    pix_list.append(pix)
                    output_pathname = os.path.join(os.path.abspath(page_output_path), f"page-{index + 1}.png")
                    pix.save(output_pathname)
                manual_pix_list.append(pix_list)
    # stepList
    step_output_path = os.path.join(output_path, "step")
    os.makedirs(step_output_path, exist_ok=True)
    existing_count = len([file for file in os.listdir(step_output_path) if file.endswith(".png")])
    if existing_count != len(item["annotationList"]) or not USE_CACHE:
        for index, step in enumerate(item["annotationList"]):
            step_pix = manual_pix_list[step["manual"]][step["page"]]
            img = Image.frombytes("RGB", (step_pix.width, step_pix.height), step_pix.samples)
            left = max(0, step["x"])
            top = max(0, step["y"])
            right = min(step["x"] + step["width"], step_pix.width)
            bottom = min(step["y"] + step["height"], step_pix.height)
            img = img.crop((left, top, right, bottom))
            output_pathname = os.path.join(os.path.abspath(step_output_path), f"step-{index + 1}.png")
            img.save(output_pathname)
    else:
        logger.info(f'steps for item {item["id"]} exist, skip')
    logger.debug(f'Finish to get manual for {item["id"]}')


def get_video(item, output_path):
    logger.debug(f'Start to get video for {item["id"]}')
    for i, video in enumerate(item["videoList"]):
        url = video["url"]
        if url:
            _get_video(url, os.path.join(output_path, "video"))
    logger.debug(f'Finish to get video for {item["id"]}')


error_item_queue = Queue()


def get_item(item):
    logger.debug(f'Start to get item {item["id"]}')
    output_path = _get_output_path(item)
    try:
        get_image(item, output_path)
        get_manual(item, output_path)
        get_video(item, output_path)
    except Exception as e:
        error_item_queue.put(item)
        logger.error(f'Error when get item {item["id"]}: {e}\n{traceback.format_exc()}')
    logger.debug(f'Finish to get item {item["id"]}')


if __name__ == "__main__":
    with open(DATASET_JSON_PATHNAME, "r", encoding="utf8") as f:
        item_list = json.load(f)
    thread_map(get_item, item_list)
    print(f"Successfully get {len(item_list) - error_item_queue.qsize()} items")
    if error_item_queue.qsize():
        print(f"Error items ({error_item_queue.qsize()}):")
        for item in error_item_queue.queue:
            print(item["id"])
