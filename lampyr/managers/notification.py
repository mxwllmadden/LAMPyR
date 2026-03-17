# -*- coding: utf-8 -*-
"""
Created on Mon Aug 25 18:44:53 2025

@author: mm4114
"""

from lampyr.managers.abstract import AbstractManager
from lampyr.files import loadjson, savejson
import requests

class NotificationManager(AbstractManager):
    def start(self):
        self.user = self.config.get('notifications.last_user')
        self.userdata = self.config.load_shared_extended_config('users')

    def add_user(self, name, service, apiid):
        pass

    def send_notification(self, message, title="Notification"):
        try:
            user_key = self.userdata.get(f'{self.user}.pushover_user_key')
            app_token = self.userdata.get(f'{self.user}.pushover_app_token')
        except KeyError:
            print('Notifications not configured — skipping push notification.')
            return

        payload = {
            "token": app_token,
            "user": user_key,
            "title": title,
            "message": message
        }

        response = requests.post("https://api.pushover.net/1/messages.json", data=payload)

        if response.status_code != 200:
            raise RuntimeError(f"Pushover notification failed: {response.text}")

        print("Notification sent successfully.")
        

if __name__ == '__main__':
    NotificationManager().send_notification('test','Lampyr')