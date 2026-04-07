# -*- coding: utf-8 -*-
"""
Created on Mon Aug 25 18:44:53 2025

@author: mm4114
"""

from lampyr.managers.abstract import AbstractManager
from lampyr.files import loadjson, savejson
import requests

class NotificationManager(AbstractManager):
    """
    Manages push notifications via the Pushover API.

    Notifications are sent to the active user and any supervisors registered
    in the shared ``users.json`` config file.

    Attributes
    ----------
    user : str
        Currently active user name (or ``'all'`` to target every user).
    userdata : ConfigFile
        Shared user database containing Pushover credentials.
    """

    def start(self):
        """Load the last-used user name and shared user database."""
        self.user = self.config.get('notifications.last_user')
        self.userdata = self.config.load_shared_extended_config('users')

    def set_user(self, name):
        """
        Set the active user and persist the choice to config.

        Parameters
        ----------
        name : str
            User name to make active.
        """
        self.user = name
        self.config.set('notifications.last_user', name)

    def add_user(self, name, pushover_user_key, pushover_app_token, supervisor=False):
        """
        Register a new user in the shared user database.

        Parameters
        ----------
        name : str
            Unique user name.
        pushover_user_key : str
            Pushover user key for the account.
        pushover_app_token : str
            Pushover application token.
        supervisor : bool, optional
            If ``True``, this user receives notifications for all other users'
            sessions.  Default is ``False``.
        """
        self.userdata._config[name] = {
            'pushover_user_key': pushover_user_key,
            'pushover_app_token': pushover_app_token,
            'supervisor': supervisor
        }
        self.userdata.save()

    def delete_user(self, name):
        """
        Remove a user from the shared user database.

        Parameters
        ----------
        name : str
            User name to delete.

        Raises
        ------
        KeyError
            If ``name`` is not in the user database.
        """
        if name not in self.userdata._config:
            raise KeyError(f"User {name!r} not found.")
        del self.userdata._config[name]
        self.userdata.save()

    def _get_targets(self):
        """
        Build the list of user names that should receive the next notification.

        Returns the active user plus any supervisors, or all users if
        ``self.user == 'all'``.

        Returns
        -------
        list of str
            Names to notify.
        """
        all_users = self.userdata.to_dict()
        if self.user == 'all':
            return list(all_users.keys())
        targets = [self.user] if self.user in all_users else []
        supervisors = [name for name, data in all_users.items()
                       if data.get('supervisor') and name != self.user]
        return targets + supervisors

    def _send_to_user(self, name, message, title):
        """
        Send a Pushover notification to a single user.

        Silently skips users whose credentials are not configured.

        Parameters
        ----------
        name : str
            User name to look up in the user database.
        message : str
            Notification body text.
        title : str
            Notification title.

        Raises
        ------
        RuntimeError
            If the Pushover API returns a non-200 status code.
        """
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
        """
        Send a notification to all target users.

        Parameters
        ----------
        message : str
            Notification body.
        title : str, optional
            Notification title. Default is ``'Notification'``.
        """
        targets = self._get_targets()
        if not targets:
            print('Notifications not configured — skipping push notification.')
            return
        for name in targets:
            self._send_to_user(name, message, title)
        

if __name__ == '__main__':
    NotificationManager().send_notification('test','Lampyr')