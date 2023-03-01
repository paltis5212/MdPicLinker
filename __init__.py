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


class MdImgUp:
    """MdImgUp 主程式"""
    upload_dict: dict[str, str] = dict()  # 上傳過的網址，以 "filename: src" 的方式儲存。
    # 設定
    config_dict: dict[str, str] = dict(
        url="http://mysite.wordpress.com/xmlrpc.php",
        username="username",
        password="password",
    )

    def init_config(self):
        """初始化設定檔"""
        # 有檔讀檔
        if Path(CONFIG_FILE_PATH).is_file():
            try:
                self.config_dict = pickle.load(open(CONFIG_FILE_PATH, "rb"))
                return
            except EOFError:
                pass
        # 寫檔
        print(f"無法讀取 `{CONFIG_FILE_PATH}`，設定檔重新建立，已恢復成預設值。\n")
        pickle.dump(self.config_dict, open(CONFIG_FILE_PATH, "w+b"))

    def input_parser(self):
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
        # 解析參數
        args = parser.parse_args()
        # 動作
        if args.subcommand == "config":
            self.command_config(is_edit=args.edit)
        elif args.subcommand == "upload":
            self.command_upload(filename=args.filename[0], is_inline=args.inline)

    def command_config(self, is_edit: bool = False):
        # 編輯
        config_dict = self.config_dict
        if is_edit:
            config_dict.update(
                url=input(f"請輸入 WordPress XML-RPC 網址 ({config_dict.get('url')})：")
                or config_dict["url"],
                username=input(f"請輸入 WordPress 帳號 ({config_dict.get('username')})：")
                or config_dict["username"],
                password=getpass("請輸入 WordPress 密碼："),
            )

            pickle.dump(config_dict, open(CONFIG_FILE_PATH, "wb"))

        print("已儲存的設定：")
        pprint({k: v for k, v in config_dict.items() if k != "password"})

    def upload_to_wordpress(self, client: Client, src: str):
        """上傳圖片到 WordPress，並回傳網址"""
        # 宣告
        filename = os.path.basename(src)
        data = {
            "name": filename,
            "type": "image/*",  # mimetype
        }
        new_src = ""
        # 獲得檔案
        data["bits"] = xmlrpc_client.Binary(open(src, "rb").read())
        # 避免重複上傳
        if filename not in self.upload_dict:
            response = client.call(media.UploadFile(data))
            new_src = response.get("url")
            print(f"已上傳圖片到 {new_src}")
            self.upload_dict[filename] = new_src
        else:
            new_src = self.upload_dict[filename]
        return new_src

    def markdown_to_html_and_upload(
        self, e: re.Match, client: Optional[Client], base_dir: str
    ):
        """Markdown 轉成 HTML。若非內聯，則上傳。"""
        # 宣告
        match = e.group(0)
        alt = e.group(1)
        src = os.path.join(base_dir, e.group(2))
        # 檢查檔案存在
        if not os.path.isfile(src):
            return match
        # 上傳處理
        if client:
            new_src = self.upload_to_wordpress(client, src)
            return f'<img alt="{alt}" src="{new_src}" />'
        # Markdown 設定
        options = dict()
        # 內聯 base64
        options.update(extensions=["pymdownx.b64"])
        return markdown.markdown(match, **options)

    def command_upload(self, filename: str, is_inline: bool = False):
        """upload 指令"""
        base_dir = os.path.dirname(filename)
        with open(filename, "r+", encoding="utf-8") as f:
            md = f.read()
            img_pattern = r"!\[(.*)\]\((.+?)\)"
            client = (
                None
                if is_inline
                else Client(
                    self.config_dict["url"],
                    self.config_dict["username"],
                    self.config_dict["password"],
                )
            )
            md = re.sub(
                img_pattern,
                lambda e: self.markdown_to_html_and_upload(e, client, base_dir),
                md,
            )
            # 覆蓋寫入
            f.seek(0)
            f.write(md)
            f.truncate()

    def cli(self):
        """執行 cli"""
        self.init_config()
        self.input_parser()
