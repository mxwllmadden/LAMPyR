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

    def _get_targets(self):
        all_users = self.userdata.to_dict()
        if self.user == 'all':
            return list(all_users.keys())
        targets = [self.user] if self.user in all_users else []
        supervisors = [name for name, data in all_users.items()
                       if data.get('supervisor') and name != self.user]
        return targets + supervisors

    def _send_to_user(self, name, message, title):
        try:
            user_key = self.userdata.get(f'{name}.pushover_user_key')
            app_token = self.userdata.get(f'{name}.pushover_app_token')
        except KeyError:
            print(f'Notifications not configured for {name!r} — skipping.')
            return
        payload = {"token": app_token, "user": user_key, "title": title, "message": message}
        response = requests.post("https://api.pushover.net/1/messages.json", data=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Pushover notification failed for {name!r}: {response.text}")
        print(f"Notification sent to {name!r}.")

    def send_notification(self, message, title="Notification"):
        targets = self._get_targets()
        if not targets:
            print('Notifications not configured — skipping push notification.')
            return
        for name in targets:
            self._send_to_user(name, message, title)
        

if __name__ == '__main__':
    NotificationManager().send_notification('test','Lampyr')