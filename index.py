from multiprocessing import JoinableQueue
from multiprocessing import Process
import serial_monitor_interface
import radar
import alert_manager
import time
import logger
from typing import Any, Protocol
from models import UltrasonicRead


class NewReadObservers(Protocol):
    def on_new_read(self, new_read: UltrasonicRead):
        pass


subscribers: list[NewReadObservers] = [
    radar,
    alert_manager,
    logger.ReadingsLogger(flush_treshold=60),
]


def fan_out(sample: dict):
    read = UltrasonicRead(**sample)
    for sub in subscribers:
        sub.on_new_read(new_read=read)


def smi_task(readins_queue: JoinableQueue, writings_queue: JoinableQueue):
    def on_next_read(sample: Any):  # actually a dict...
        readins_queue.put(sample)

    smi = serial_monitor_interface.SerialMonitorInterface(
        on_next_read=on_next_read, messages_to_send_queue=writings_queue
    )
    # fan in - single producer
    smi.start()

    while True:
        # stay alive
        time.sleep(60)

    # send a signal that no further tasks are coming
    readins_queue.put(None)


def app_task(readins_queue: JoinableQueue, writings_queue: JoinableQueue):
    # process items from the queue
    iteration = 0

    while True:
        # get a task from the queue
        sample = readins_queue.get()
        # check for signal that we are done
        if sample is None:
            break
        # process
        fan_out(sample=sample)
        # mark the unit of work as processed
        readins_queue.task_done()
        iteration = (iteration + 1) % 10
        if iteration % 10 == 0:
            writings_queue.put("<some_num=4 some_num2=14 some_str=hakuna matata>")

    # mark the signal as processed
    readins_queue.task_done()
    print("Consumer finished", flush=True)


# entry point
if __name__ == "__main__":
    readins_queue = JoinableQueue()
    writings_queue = JoinableQueue()

    smi_process = Process(
        target=smi_task,
        args=(
            readins_queue,
            writings_queue,
        ),
        daemon=True,
    )
    smi_process.start()

    app_process = Process(
        target=app_task,
        args=(
            readins_queue,
            writings_queue,
        ),
        daemon=True,
    )
    app_process.start()

    app_process.join()

    readins_queue.join()
    writings_queue.join()
    print("Main found that all tasks are processed", flush=True)
