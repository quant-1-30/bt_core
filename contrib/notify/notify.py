#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor


__all__ = ['async_email']


def send_email(subject, body, to_email, from_email, smtp_server, smtp_port, login, password):
    # Create a multipart message
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    # Attach the body with the msg instance
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to the server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Secure the connection

        # Login to the email account
        server.login(login, password)

        # Send the email
        server.sendmail(from_email, to_email, msg.as_string())

        # Disconnect from the server
        server.quit()

        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")


async def async_email(subject, body, to_email, from_email, smtp_server, smtp_port, login, password):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        await loop.run_in_executor(
            executor,
            send_email,
            subject, body, to_email, from_email, smtp_server, smtp_port, login, password
        )


# class EmailEngine:
#     """
#     Provides email sending function.
#     """

#     def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
#         """"""
#         super(EmailEngine, self).__init__(main_engine, event_engine, "email")

#         self.thread: Thread = Thread(target=self.run)
#         self.queue: Queue = Queue()
#         self.active: bool = False

#         self.main_engine.send_email = self.send_email

#     def send_email(self, subject: str, content: str, receiver: str = "") -> None:
#         """"""
#         # Start email engine when sending first email.
#         if not self.active:
#             self.start()

#         # Use default receiver if not specified.
#         if not receiver:
#             receiver: str = SETTINGS["email.receiver"]

#         msg: EmailMessage = EmailMessage()
#         msg["From"] = SETTINGS["email.sender"]
#         msg["To"] = receiver
#         msg["Subject"] = subject
#         msg.set_content(content)

#         self.queue.put(msg)

#     def run(self) -> None:
#         """"""
#         server: str = SETTINGS["email.server"]
#         port: int = SETTINGS["email.port"]
#         username: str = SETTINGS["email.username"]
#         password: str = SETTINGS["email.password"]

#         while self.active:
#             try:
#                 msg: EmailMessage = self.queue.get(block=True, timeout=1)

#                 try:
#                     with smtplib.SMTP_SSL(server, port) as smtp:
#                         smtp.login(username, password)
#                         smtp.send_message(msg)
#                 except Exception:
#                     msg: str = _("邮件发送失败: {}").format(traceback.format_exc())
#                     self.main_engine.write_log(msg, "EMAIL")
#             except Empty:
#                 pass

#     def start(self) -> None:
#         """"""
#         self.active = True
#         self.thread.start()

#     def close(self) -> None:
#         """"""
#         if not self.active:
#             return

#         self.active = False
#         self.thread.join()
