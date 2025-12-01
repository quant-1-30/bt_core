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
