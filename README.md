asyncSSH
========

send asynchronous command via SSH 

```
ran@localhost $ ./asyncSSH.py --help
Usage: asyncSSH.py [options]

Options:
  -h, --help            show this help message and exit
  -t TARGET, --target=TARGET
                        remote host ip / fqdn
  -k KEY, --key=KEY     ssh private key
  -p PORT, --port=PORT  ssh port
  -u USER, --user=USER  ssh username
  -i INTERVAL, --interval=INTERVAL
                        how many times we should wait for the script to end
  -s SLEEP, --sleep=SLEEP
                        how many seconds to wait in each interval
```
