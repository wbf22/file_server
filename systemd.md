
sudo systemctl stop bsync.service
sudo cp ~/Documents/file_server/bsync.service /etc/systemd/system

sudo systemctl daemon-reload
sudo systemctl enable bsync.service
sudo systemctl start bsync.service
sudo systemctl status bsync.service


sudo journalctl -u bsync.service -f