Wort fermentation control.

py/ code runs on a raspberry pi with ds18b20 sensors.
Dependencies can be installed with pip from requirements.txt

This is implemented using gevent so the fridge, sensors, uploader
etc are each written as independent tasks.

---

web/ code is a Bottle web app for showing graphs and also
controlling the temperature from a phone-optimised UI

https://evil.ucc.asn.au/~matt/templog/ is live

![graph](templog.png)

![parameters](webparams.png)
---

old/ is the previous version that ran on an avr talking over a serial bluetooth device
with a separate internet-connected router relaying to the web interface.


Matt Johnston
matt@ucc.asn.au
