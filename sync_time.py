import network
import ntptime
import machine
import time

def ntp_sync():
    """
    micropython protocol to sync the rtc with the current localtime
    needs a functioning wifi connection
    """
    # try to connect to wifi
    # wlan = network.WLAN(network.STA_IF)
    # wlan.active(True)
    # wlan.connect("SSID", "Passwort")

    # while not wlan.isconnected():
    #     time.sleep(1)
    # print("Verbunden!", wlan.ifconfig())

    # load ntp-time and sync it with the local rtc
    try:
        ntptime.settime()
        print("Zeit synchronisiert:", time.localtime())
    except:
        print("NTP-Sync fehlgeschlagen")

    # RTC auslesen
    rtc = machine.RTC()
    print("RTC Zeit:", rtc.datetime())

if __name__ == '__main__':
    ntp_sync()
