# Cam
Service running on a raspberry pi to take recordings in H264 format.

If the raspberry pi cannot connect to a wifi it starts a hotspot, such that the service is still accessable.

Service can be accessed via the port `80` or `8000`. If connected via the hotspot the ip address will be `192.168.12.1`.

## Schedule

The format for the schedule is

```
HH:[MM]-HH:[MM](,HH:[MM]-HH:[MM])*
```

Examples are: `0-24`, `8-20`, `8:30-19:24` or multiple ranges like `8-10:30,16:30-20`.

## Recordings

Recordings cam be found in the folder `cam/src/recordings`.

## Install

Install a fresh raspberry lite and log in (e.g. via ssh).

Execute the following command while replacing `<ssid>` with the SSID for the hotspot and `<password>` with the password of the hotspot (it needs at least 8 characters):

```
curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/eikemueller/cam/main/install.sh | sudo bash -s <ssid> <password>
```

## Todo

 - Allow downloading/deleting of recording via service. Currently needs to be done e.g. via `ssh`/`scp` or by taking out the sd card.
 - Sync time automatically when opening website