import argparse
import os
import pickle
import re
from getpass import getpass
from pathlib import Path
from pprint import pprint
from typing import Optional

import markdown
from wordpress_xmlrpc import Client
from wordpress_xmlrpc.compat import xmlrpc_client
from wordpress_xmlrpc.methods import media

CONFIG_FILE_PATH = "config.pickle"  # config 路徑
UPLOAD_DICT: dict[str, str] = dict()  # 上傳過的網址，以 "filename: src" 的方式儲存。


def init_config():
    """初始化設定檔"""
    # 沒有檔案時初始化設定檔
    if not Path(CONFIG_FILE_PATH).is_file():
        with open(CONFIG_FILE_PATH, "w+b") as f:
            pickle.dump(
                dict(
                    url="http://mysite.wordpress.com/xmlrpc.php",
                    username="username",
                    password="password",
                ),
                f,
            )


def input_parser():
    """參數控制"""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand")

    # config 參數
    config_parser = subparsers.add_parser("config", help="設定檔操作，無參數則顯示設定檔內容。")
    config_parser.add_argument("-e", "--edit", action="store_true", help="編輯")

    # upload 參數
    upload_parser = subparsers.add_parser(
        "upload", help="Markdown 的圖片上傳，並覆寫圖片區塊成 HTML。"
    )
    upload_parser.add_argument(
        "--inline",
        action="store_true",
        help="開啟則將圖片內聯成 base64 格式，而不是上傳到遠端。預設關閉，不建議使用。",
    )
    upload_parser.add_argument("filename", nargs=1, help="讀取的 Markdown 檔名。")

    # 收穫參數
    return parser


def read_config():
    """讀取設定"""
    config_dict: dict[str, str]
    with open(CONFIG_FILE_PATH, "rb") as f:
        config_dict = pickle.load(f)

    return config_dict


def command_config(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config_dict: dict[str, str],
):
    """config 指令"""
    # 編輯
    if args.edit:
        if temp := input(f"請輸入 WordPress XML-RPC 網址 ({config_dict.get('url')})："):
            config_dict["url"] = temp
        if temp := input(f"請輸入 WordPress 帳號 ({config_dict.get('username')})："):
            config_dict["username"] = temp
        config_dict["password"] = getpass("請輸入 WordPress 密碼：")

        with open(CONFIG_FILE_PATH, "wb") as f:
            pickle.dump(config_dict, f)

    print("已儲存的設定：")
    pprint({k: v for k, v in config_dict.items() if k != "password"})
    parser.exit(0)


def upload_to_wordpress(client: Client, src: str):
    """上傳圖片到 WordPress，並回傳網址"""
    # 宣告
    filename = os.path.basename(src)
    data = {
        "name": filename,
        "type": "image/*",  # mimetype
    }
    new_src = ""
    # 獲得檔案
    with open(src, "rb") as img:
        data["bits"] = xmlrpc_client.Binary(img.read())
    # 避免重複上傳
    if filename not in UPLOAD_DICT.keys():
        response = client.call(media.UploadFile(data))
        new_src = response.get("url")
        print(f"已上傳圖片到 {new_src}")
        UPLOAD_DICT[filename] = new_src
    else:
        new_src = UPLOAD_DICT[filename]
    return new_src


def markdown_to_html_and_upload(
    e: re.Match, client: Optional[Client], is_inline: bool = False
):
    """Markdown 轉成 HTML。若非內聯，則上傳。"""
    # 宣告
    match = e.group(0)
    alt = e.group(1)
    src = e.group(2)
    # 檢查檔案存在
    if not os.path.isfile(src):
        return match
    # Markdown 設定
    options = dict()
    # 內聯 base64
    if is_inline:
        options.update(extensions=["pymdownx.b64"])
        return markdown.markdown(match, **options)
    # 上傳處理
    new_src = upload_to_wordpress(client, src)
    return f'<img alt="{alt}" src="{new_src}" />'


def command_upload(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config_dict: dict[str, str],
):
    """upload 指令"""
    with open(args.filename[0], "r+") as f:
        md = f.read()
        img_pattern = r"!\[(.*)\]\((.+?)\)"
        md = re.sub(
            img_pattern,
            lambda e: markdown_to_html_and_upload(
                e,
                None
                if args.inline
                else Client(
                    config_dict["url"], config_dict["username"], config_dict["password"]
                ),
                args.inline,
            ),
            md,
        )
        # 覆蓋寫入
        f.seek(0)
        f.write(md)
        f.truncate()


def main():
    init_config()
    parser = input_parser()
    args = parser.parse_args()
    config_dict = read_config()
    # 動作
    match args.subcommand:
        case "config":
            command_config(parser, args, config_dict)
        case "upload":
            command_upload(parser, args, config_dict)


if __name__ == "__main__":
    main()
