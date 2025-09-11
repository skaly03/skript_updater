import time
import os

class RotatingLogger:
    DEBUG   = 10
    INFO    = 20
    WARNING = 30
    ERROR   = 40
    CRITICAL= 50

    LEVEL_NAMES = {
        DEBUG:    "DEBUG",
        INFO:     "INFO",
        WARNING:  "WARNING",
        ERROR:    "ERROR",
        CRITICAL: "CRITICAL"
    }

    def __init__(self, name="Logger", console_level=DEBUG, file_level=WARNING, filename="log.txt", max_size=50*1024):
        self.name = name
        self.console_level = console_level
        self.file_level = file_level
        self.filename = filename
        self.max_size = max_size
        self.logfile = None
        if self.filename:
            self._open_logfile()

    def _open_logfile(self):
        try:
            self.logfile = open(self.filename, "a")
        except Exception as e:
            print("Logger: Fehler beim Öffnen der Logdatei:", e)
            self.logfile = None

    def _should_rotate(self):
        if self.logfile is None:
            return False
        try:
            self.logfile.flush()
            stat = os.stat(self.filename)
            return stat[6] > self.max_size  # size in bytes
        except:
            return False

    def _rotate(self):
        try:
            if self.logfile is not None:
                self.logfile.close()
            if os.path.exists(self.filename + ".old"):
                os.remove(self.filename + ".old")
            if os.path.exists(self.filename):
                os.rename(self.filename, self.filename + ".old")
            self._open_logfile()
        except Exception as e:
            print("Logger: Fehler beim Rotieren der Logdatei:", e)

    def _timestamp(self):
        try:
            t = time.localtime()
            return "%04d-%02d-%02d %02d:%02d:%02d" % (t[0],t[1],t[2],t[3],t[4],t[5])
        except:
            return "0000-00-00 00:00:00"

    def _log(self, level, msg, *args):
        levelname = self.LEVEL_NAMES.get(level, str(level))
        message = msg % args if args else msg
        log_line = "%s [%s] %s: %s" % (self._timestamp(), levelname, self.name, message)

        # Shell ausgabe für alle log-level
        if level >= self.console_level:
            print(log_line)

        # File logging nur für WARNING+
        if level >= self.file_level and self.logfile:
            try:
                if self._should_rotate():
                    self._rotate()
                self.logfile.write(log_line + "\n")
                self.logfile.flush()
            except Exception as e:
                print("Logger: Fehler beim Schreiben in Logdatei:", e)

    def debug(self, msg, *args):    self._log(self.DEBUG, msg, *args)
    def info(self, msg, *args):     self._log(self.INFO, msg, *args)
    def warning(self, msg, *args):  self._log(self.WARNING, msg, *args)
    def error(self, msg, *args):    self._log(self.ERROR, msg, *args)
    def critical(self, msg, *args): self._log(self.CRITICAL, msg, *args)

    def close(self):
        if self.logfile:
            self.logfile.close()
            self.logfile = None

# logger = RotatingLogger(
#     name="MeinModul",
#     console_level=RotatingLogger.DEBUG,   # alle Logs in Shell
#     file_level=RotatingLogger.WARNING,    # nur Warnings und höher in Datei
#     filename="log.txt",
#     max_size=50*1024  # 50 KB max Größe
# )

# logger.debug("Debug Nachricht: %s", "Test")
# logger.info("Infos sind sichtbar.")
# logger.warning("Warnung! Speicher fast voll.")
# logger.error("Fehlercode: %d", 42)
# logger.critical("Kritischer Fehler!")

# logger.close()
