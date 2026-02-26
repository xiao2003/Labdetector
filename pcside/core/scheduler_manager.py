# pcside/core/scheduler_manager.py
from apscheduler.schedulers.background import BackgroundScheduler
from pcside.core.logger import console_info
from pcside.core.tts import speak_async

class SchedulerManager:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(self._morning_routine, 'cron', hour=8, minute=30)
        self.scheduler.add_job(self._evening_routine, 'cron', hour=17, minute=30)

    def _morning_routine(self):
        msg = "早上好，今天进行实验时，请务必佩戴护目镜和手套。"
        console_info(f"⏰ 定时广播: {msg}")
        speak_async(msg)

    def _evening_routine(self):
        msg = "离开实验室前，请检查废液桶是否盖紧，水电气是否关闭。"
        console_info(f"⏰ 定时广播: {msg}")
        speak_async(msg)

    def start(self):
        self.scheduler.start()
        console_info("主动安全定时广播任务引擎已启动")

    def stop(self):
        self.scheduler.shutdown()

scheduler_manager = SchedulerManager()