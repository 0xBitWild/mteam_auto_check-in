"""mteam自动签到脚本。"""

import os
import json
import time
import random
import logging
import smtplib
from email.mime.text import MIMEText
from pathlib import Path


import pyotp
import requests
import schedule
from playwright.sync_api import sync_playwright, Page
from playwright.sync_api import (TimeoutError as PlaywrightTimeoutError,
                                 Error as PlaywrightError)

# 配置日是记录器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(filename)s - %(lineno)d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    # filename=Path(__file__).stem + '.log',
    filemode='a'
)
logger = logging.getLogger(__name__)


class LocalStorageLoginError(Exception):
    """LocalStorage登录失败异常。"""


class PasswordLoginError(Exception):
    """密码登录失败异常。"""


class NotificationSender:
    """通知发送类，支持多种通知方式。"""

    def __init__(self):
        self.smtp_config = None
        self.telegram_config = None

    def configure_smtp(self, host, port, username, password):
        """配置SMTP服务器信息。"""
        self.smtp_config = {
            'host': host,
            'port': port,
            'username': username,
            'password': password
        }

    def configure_telegram(self, bot_token, chat_id):
        """配置Telegram机器人信息。"""
        self.telegram_config = {
            'bot_token': bot_token,
            'chat_id': chat_id
        }

    def send_smtp(self, subject, message, to_email):
        """通过SMTP发送邮件通知。"""
        if not self.smtp_config:
            raise ValueError("SMTP配置未设置")

        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = self.smtp_config['username']
        msg['To'] = to_email

        try:
            with smtplib.SMTP_SSL(self.smtp_config['host'], int(self.smtp_config['port']), timeout=30) as server:
                server.login(self.smtp_config['username'], self.smtp_config['password'])
                logger.info("SMTP登录成功")
                server.send_message(msg)
                logger.info("SMTP邮件发送成功")
                server.quit()
        except smtplib.SMTPException as e:
            logger.error("发送邮件时发生未知错误: %s", str(e))

    def send_telegram(self, message):
        """通过Telegram发送通知。"""
        if not self.telegram_config:
            raise ValueError("Telegram配置未设置")

        url = f"https://api.telegram.org/bot{self.telegram_config['bot_token']}/sendMessage"
        payload = {
            'chat_id': self.telegram_config['chat_id'],
            'text': message
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Telegram消息发送成功")
        except requests.RequestException as e:
            logger.error("Telegram消息发送失败: %s", str(e))

    def send_notification(self, message, subject=None):
        """发送通知，根据配置选择发送方式。"""
        to_email = os.environ.get('NOTIFY_EMAIL')
        if self.smtp_config and to_email:
            self.send_smtp(subject or "通知", message, to_email)
        if self.telegram_config:
            self.send_telegram(message)


class LocalStorageManager:
    """Local Storage管理类。"""

    def __init__(self, page: Page) -> None:
        self.page = page

    def get_value(self, key: str) -> str:
        """获取Local Storage中的值。"""
        return self.page.evaluate(f'localStorage.getItem("{key}")')

    def set_value(self, key: str, value: str) -> None:
        """设置Local Storage中的值。"""
        escaped_value = json.dumps(value)
        self.page.evaluate(f'localStorage.setItem("{key}", {escaped_value})')

    def remove_value(self, key: str) -> None:
        """删除Local Storage中的指定键值对。"""
        self.page.evaluate(f'localStorage.removeItem("{key}")')

    def clear(self) -> None:
        """清空Local Storage中的所有数据。"""
        self.page.evaluate('localStorage.clear()')

    def save_to_file(self, filename: str) -> None:
        """将Local Storage保存到本地json文件。"""
        storage_data = self.page.evaluate('() => JSON.stringify(localStorage)')
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json.loads(storage_data), f, ensure_ascii=False, indent=4)

    def load_from_file(self, filename: str) -> None:
        """从本地json文件加载数据到Local Storage。"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                storage_data = json.load(f)
            for key, value in storage_data.items():
                try:
                    self.set_value(key, value)
                except (PlaywrightError, ValueError) as e:
                    logger.error("设置键 '%s' 的值时出错: %s", key, str(e))
        except FileNotFoundError:
            logger.warning("文件 %s 不存在，无法加载Local Storage数据。", filename)
        except json.JSONDecodeError:
            logger.error("文件 %s 不是有效的JSON格式，无法加载Local Storage数据。", filename)
        except IOError as e:
            logger.error("读取文件 %s 时发生I/O错误: %s", filename, str(e))
        except Exception as e:
            logger.error("加载Local Storage数据时发生未预期的错误: %s", str(e))
            raise  # 重新抛出异常，以便进一步调查


class MTeamSpider:
    """M-Team 自动签到爬虫类。"""

    def __init__(self) -> None:

        self.localstorage_file = Path(__file__).parent / 'mteam_localstorage.json'
        self.username = os.environ.get('MTEAM_USERNAME')
        self.password = os.environ.get('MTEAM_PASSWORD')
        self.totp_secret = os.environ.get('MTEAM_TOTP_SECRET')

        self.notify_subject = 'M-Team签到脚本通知'

        if not all([self.username, self.password, self.totp_secret]):
            raise ValueError("请设置所有必要的环境变量：MTEAM_USERNAME, MTEAM_PASSWORD, MTEAM_TOTP_SECRET")

        notify_type = os.environ.get('NOTIFY_TYPE')

        self.notifier = NotificationSender()

        if notify_type == 'smtp':

            if not all([os.environ.get('SMTP_HOST'),
                        os.environ.get('SMTP_PORT'),
                        os.environ.get('SMTP_USERNAME'),
                        os.environ.get('SMTP_PASSWORD')]
                       ):
                raise ValueError("请设置所有必要的环境变量：SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD")

            self.notifier.configure_smtp(
                os.environ.get('SMTP_HOST'),
                os.environ.get('SMTP_PORT'),
                os.environ.get('SMTP_USERNAME'),
                os.environ.get('SMTP_PASSWORD')
            )

            self.notifier.send_notification('SMTP配置成功', subject=self.notify_subject)

        elif notify_type == 'telegram':

            if not all([os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')]):
                raise ValueError("请设置所有必要的环境变量：TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")

            self.notifier.configure_telegram(
                os.environ.get('TELEGRAM_BOT_TOKEN'),
                os.environ.get('TELEGRAM_CHAT_ID')
            )

            self.notifier.send_notification('Telegram配置成功', subject=self.notify_subject)

        elif notify_type == 'none':
            self.notifier = None
            logger.warning("未设置通知类型，将不发送通知")
        else:
            raise ValueError("通知类型必须是 'smtp' 或 'telegram' 或 'none'")

    def _get_captcha_code(self) -> str:

        totp = pyotp.TOTP(self.totp_secret)
        captcha_code = totp.now()

        return captcha_code

    @staticmethod
    def _is_login_successful(page: Page):

        # 检查是否成功登录
        if page.url == 'https://kp.m-team.cc/index':
            return True

        return False

    def login_by_localstorage(self, page: Page, local_storage_manager: LocalStorageManager) -> None:
        """使用保存的 localstorage 数据尝试登录 M-Team。"""
        try:
            local_storage_manager.load_from_file(str(self.localstorage_file))

            # 刷新页面
            page.reload()

            # 等待页面加载完成
            page.wait_for_load_state('networkidle')

            # 检查是否成功登录
            if self._is_login_successful(page):
                logger.info('通过 localStorage 登录 M-Team 成功')

                # 保存localstorage到文件
                local_storage_manager.save_to_file(str(self.localstorage_file))
                logger.info('已保存更新localstorage到文件')

                self.notifier.send_notification('通过 localStorage 登录 M-Team 成功', subject=self.notify_subject)
            else:
                logger.warning('通过 localStorage 登录 M-Team 失败')
                raise LocalStorageLoginError('通过 localStorage 登录 M-Team 失败')

        except Exception as e:
            logger.error('通过 localStorage 登录时发生错误: %s', str(e))
            raise LocalStorageLoginError(str(e)) from e

    def login_by_password(self, page: Page, local_storage_manager: LocalStorageManager) -> None:
        """使用用户名和密码登录 M-Team。"""

        try:

            if page.url != 'https://kp.m-team.cc/login':
                # 访问登录页
                page.goto('https://kp.m-team.cc/login')

            # 等待页面加载完成
            page.wait_for_load_state('networkidle')

            # 输入用户名/密码
            page.locator('button[type="submit"]').wait_for()
            page.locator('input[id="username"]').fill(self.username)
            page.locator('input[id="password"]').fill(self.password)
            page.locator('button[type="submit"]').click()

            try:
                # 等待2FA页面加载完成
                page.locator('input[id="otpCode"]').wait_for()

                # 获取并输入2FA验证码
                captcha_code = self._get_captcha_code()
                page.locator('input[id="otpCode"]').fill(captcha_code)
                page.locator('button[type="submit"]').click()

                # 等待页面加载完成
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(5000)

            except PlaywrightTimeoutError as e:
                logger.warning('处理2FA时发生超时错误: %s', str(e))
            except PlaywrightError as e:
                logger.warning('处理2FA时发生Playwright错误: %s', str(e))

            if self._is_login_successful(page):
                logger.info('通过用户名密码登录M-Team成功')

                # 如果文件存在，则删除
                if self.localstorage_file.exists():
                    self.localstorage_file.unlink()

                # 保存localstorage到文件
                local_storage_manager.save_to_file(str(self.localstorage_file))
                logger.info('已保存localstorage到文件')

                self.notifier.send_notification('通过用户名密码登录M-Team成功', subject=self.notify_subject)

            else:
                logger.error('通过用户名密码登录M-Team失败')

                raise PasswordLoginError('通过用户名密码登录M-Team失败')

        except Exception as e:
            logger.error('通过用户名密码登录时发生错误: %s', str(e))

            self.notifier.send_notification(f'通过用户名密码登录时发生错误: {str(e)}', subject=self.notify_subject)

            raise PasswordLoginError(str(e)) from e

    def check_in(self):
        """执行M-Team自动签到流程。"""

        logger.info("开始执行签到流程")

        # 随机等待10到300秒
        random_delay = random.randint(10, 300)
        logger.info("等待 %s 秒后开始签到", random_delay)
        time.sleep(random_delay)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                # 首先导航到M-Team网站
                page.goto('https://kp.m-team.cc/')

                # 等待页面加���完成
                page.wait_for_load_state('networkidle')

                # 创建Local Storage管理器
                local_storage_manager = LocalStorageManager(page)

                # 尝试使用localStorage登录
                self.login_by_localstorage(page, local_storage_manager)
            except LocalStorageLoginError:
                # 如果localStorage登录失败，尝试使用密码登录
                self.login_by_password(page, local_storage_manager)
            finally:
                browser.close()

    def schedule_check_in(self):
        """定时签到。"""

        logger.info('定时签到任务开始...')

        # 生成9:00到12:00之间的随机时间
        random_hour = random.randint(9, 11)
        random_minute = random.randint(0, 59)
        random_time = f"{random_hour:02d}:{random_minute:02d}"

        # 每天在生成的随机时间签到
        schedule.every().day.at(random_time).do(self.check_in)

        logger.info("已设置每天 %s 进行签到", random_time)

        # 每小时执行一次心跳
        def heartbeat():
            logger.info('定时签到任务正在运行...')

        schedule.every().hour.do(heartbeat)

        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == '__main__':

    MTeamSpider().schedule_check_in()
