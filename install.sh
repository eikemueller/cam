#!/bin/bash
#

if [[ `env | grep ^USER | cut -d "=" -f 2` != "root" ]]
then
  echo "Please run as root"
  exit 1
fi
CAM_USER=`env | grep ^SUDO_USER | cut -d "=" -f 2`
if [[ "$CAM_USER" == "" ]]
then
  CAM_USER="root"
fi
HOTSPOT_SSID="$1"
HOTSPOT_PW="$2"

echo "Setup with CAM_USER=$CAM_USER, HOTSPOT_SSID=$HOTSPOT_SSID, HOTSPOT_PW=$HOTSPOT_PW"

echo "Installing dependecies"
apt-get -y install git util-linux procps hostapd iproute2 iw dnsmasq iptables python3-opencv

echo "Installing create_ap"
git clone https://github.com/lakinduakash/linux-wifi-hotspot
cd linux-wifi-hotspot/src/scripts
sed -i 's/ExecStart=/PreExecStart=sleep 30\nExecStart=/g' create_ap.service
make install-cli-only
create_ap -n wlan0 "$HOTSPOT_SSID" "$HOTSPOT_PW" --mkconfig /etc/create_ap.conf
cd ../../..

echo "Installing cam"
git clone https://github.com/eikemueller/cam.git
cd cam
sed -i "s/_USER_/$CAM_USER/g" cam.service
sed -i "s#_PATH_#$PWD#g" cam.service
install -CDm644 cam.service /lib/systemd/system/cam.service
cd ..

echo "Activating services"
systemctl enable create_ap
systemctl enable cam