import argparse
import os
import pickle
import re
from getpass import getpass
from pathlib import Path
from pprint import pprint
from typing import Optional
from dataclasses import dataclass
import markdown
from wordpress_xmlrpc import Client
from wordpress_xmlrpc.compat import xmlrpc_client
from wordpress_xmlrpc.methods import media

CONFIG_FILE_PATH = "config.pickle"  # config 路徑


@dataclass
class MdImgsUpConfig:
    """設定"""

    url: str
    username: str
    password: str


class MdImgsUp:
    """MdImgsUp 主程式"""

    uploaded_dict: dict[str, str] = dict()  # 上傳過的網址，以 "filename: src" 的方式儲存。
    # 設定
    config: MdImgsUpConfig = MdImgsUpConfig(
        url="http://mysite.wordpress.com/xmlrpc.php",
        username="username",
        password="password",
    )

    def init_config(self):
        """初始化設定檔"""
        # 有檔讀檔
        if Path(CONFIG_FILE_PATH).is_file():
            try:
                self.config: MdImgsUpConfig = pickle.load(open(CONFIG_FILE_PATH, "rb"))
                return
            except EOFError:
                pass
        # 寫檔
        print(f"無法讀取 `{CONFIG_FILE_PATH}`，設定檔重新建立，已恢復成預設值。\n")
        pickle.dump(self.config, open(CONFIG_FILE_PATH, "w+b"))

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
        upload_parser.add_argument("filepath", nargs=1, help="讀取的 Markdown 檔名。")
        # 解析參數
        args = parser.parse_args()
        # 動作
        if args.subcommand == "config":
            self.command_config(is_edit=args.edit)
        elif args.subcommand == "upload":
            self.command_upload(filepath=args.filepath[0], is_inline=args.inline)
        else:
            print("未知的指令，請用 -h 查看幫助。")

    def command_config(self, is_edit: bool = False):
        """設定檔操作"""
        # 編輯
        if is_edit:
            self.config.update(
                url=input(f"請輸入 WordPress XML-RPC 網址 ({self.config.url})：")
                or self.config.url,
                username=input(f"請輸入 WordPress 帳號 ({self.config.username})：")
                or self.config.username,
                password=getpass("請輸入 WordPress 密碼：") or self.config.password,
            )
            pickle.dump(self.config, open(CONFIG_FILE_PATH, "wb"))
        print("已儲存的設定：")
        pprint({k: v for k, v in vars(self.config).items() if k != "password"})

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
        if filename not in self.uploaded_dict:
            response = client.call(media.UploadFile(data))
            new_src = response.get("url")
            print(f"已上傳圖片到 {new_src}")
            self.uploaded_dict[filename] = new_src
        else:
            new_src = self.uploaded_dict[filename]
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

    def command_upload(self, filepath: str, is_inline: bool = False):
        """upload 指令"""
        base_dir = os.path.dirname(filepath)
        with open(filepath, "r+", encoding="utf-8") as f:
            md = f.read()
            img_pattern = r"!\[(.*)\]\((.+?)\)"
            client = (
                None
                if is_inline
                else Client(
                    self.config.url,
                    self.config.username,
                    self.config.password,
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
        """Execute the cli."""
        self.init_config()
        self.input_parser()
