"""This module handles displaying lights on the device for complex visualizations

It runs the light_string in a second thread constantly refreshing it based on what
 exists in the DynamicDisplay class pixel_array like a primitive display driver. This
 array is shared with the main thread and is thread safe, so it can be updated while
 ignoring the display refresh cycles and will update the display device on the
 next cycle.
"""
from multiprocessing import Process, Array
from typing import Callable, List
import time
from rpi_ws281x import Color
from config import log

from classes.SpotifyAudioAnalysis import SpotifyAudioAnalysis
from classes.LedColor import LedColor


class DynamicDisplay:
    def __init__(self, light_string):
        self.light_string = light_string
        self.groups = {}
        self.group_threads = {}
        self.light_refresh_loop = None
        self.pixel_array = Array("l", light_string.led_count)

    def reinitialize(self):
        self.terminate_all_running_process()
        self.pixel_array = None
        self.pixel_array = Array("l", self.light_string.led_count)
        self.__start_refresh_thread()
        log.info(
            "All threads stopped, pixel_array reinitialized and display thread"
            " restarted."
        )

    def __terminate_string_refresh_loop(self):
        if self.light_refresh_loop:
            self.light_refresh_loop.terminate()

    def terminate_all_running_process(self):
        """End all processes associated with the class. Meant to be run in the finally
        block anytime the class is instantiated.
        """
        if not self.light_refresh_loop:
            return

        self.light_refresh_loop.terminate()

        # Terminate all open animation threads
        for key in self.group_threads.keys():
            self.group_threads[key].terminate()

    def __start_refresh_thread(self):
        self.light_refresh_loop = Process(
            target=self.__refresh_loop, args=[self.pixel_array]
        )
        self.light_refresh_loop.start()

    def __refresh_loop(self, pixel_array):
        while True:
            for pixel_n, color in enumerate(pixel_array):
                self.light_string.strip.setPixelColor(pixel_n, color)

            self.light_string.strip.show()
            time.sleep(0.005)

    def __start_thread_for_group(
        self,
        group_name: str,
        target: Callable,
        args: list = [],
        kwargs: dict = {},
    ):
        log.info(f"Starting thread for group {group_name}")
        self.group_threads[group_name] = Process(
            target=target, args=args, kwargs=kwargs
        )
        self.group_threads[group_name].start()

    def update_group(self, group_name: str, color: Color):
        """Updates every pixel in the group to the provided color

        Args:
            group_name (str): Key in groups dict to get pixel numbers from
            color (Color): Color to update those pixels too
        """
        for pixel_n in self.groups[group_name]:
            self.pixel_array[pixel_n] = color

    def create_group_of_every_nth(self, n: int, offset: int, group_name: str):
        group_pixels = []

        for i in range(self.light_string.led_count):
            if i % n == offset:
                group_pixels.append(i)

        self.groups[group_name] = group_pixels

    def run_group_on_item(
        self,
        audio_analysis: SpotifyAudioAnalysis,
        group_name: str,
        nth_item: int,
        item: str = "beats",
        colors: List[Color] = None,
        color_change_on: str = "bars",
    ):
        """Sets up a lighting pattern using item for the key grabbed in Audio Analysis

        Args:
            audio_analysis (SpotifyAudioAnalysis) : Audio analysis controller
            group_name (str): Key in groups dict to get pixel numbers from
            nth_item (int): Activate pixel on every nTh item
            item (str): Which specific key in the audio analysis to use
            colors (List[Color]): Colors to use for lighting pattern. Uses a random
                color if no list is provided
            color_change_on (str): Key to watch for from Audio Analysis to make color
                changes on
        """
        last_active = {}
        rgb_black = [0, 0, 0]
        color = LedColor.black

        while (
            audio_analysis.get_track_progress_seconds()
            < audio_analysis.track_duration * 1000
        ):
            now_active = audio_analysis.get_active_binary_search()

            if not now_active:
                self.__terminate_string_refresh_loop()
                self.light_string.set_solid(LedColor.black)
                return

            if now_active.get(color_change_on) and (
                not last_active.get(color_change_on)
                == now_active.get(color_change_on)
            ):
                color = (
                    LedColor.get_random()
                    if not colors
                    else colors[
                        now_active.get(color_change_on)["index"] % len(colors)
                    ]
                )

            active_item = now_active.get(item)

            if (
                not active_item
                or active_item["confidence"]
                < audio_analysis.confidence_average[item] * 0.5
            ):
                time.sleep(0.01)
                continue

            if active_item and (not last_active.get(item) == active_item):
                if active_item["index"] % nth_item == 0:
                    self.update_group(group_name, color)
                    start_color_list = LedColor.get_rgb_value(color)
                    for i in range(100):
                        time.sleep(
                            ((active_item["duration"] / 100) * nth_item) * 0.5
                        )
                        mid_color = LedColor.interpolate_rgb(
                            start_color_list, rgb_black, i / 100
                        )
                        self.update_group(group_name, Color(*mid_color))

            last_active = now_active

    def dual_beats(self, audio_analysis: SpotifyAudioAnalysis):
        self.groups = {}

        log.info("Starting dual beats.")

        self.create_group_of_every_nth(n=2, offset=0, group_name="all_beat")
        self.create_group_of_every_nth(
            n=2, offset=1, group_name="every_2nd_beat"
        )

        all_beat = {
            "target": self.run_group_on_item,
            "args": [audio_analysis, "all_beat", 1],
            "kwargs": {
                "color_change_on": "beats",
                "item": "beats",
                "colors": [
                    Color(
                        255,
                        0,
                        0,
                    ),
                    Color(
                        255,
                        255,
                        255,
                    ),
                ],
            },
        }
        every_2nd_beat = {
            "target": self.run_group_on_item,
            "args": [audio_analysis, "every_2nd_beat", 2],
            "kwargs": {
                "item": "beats",
                "colors": [
                    LedColor.green,
                    LedColor.autumnOrange,
                    LedColor.brightViolet,
                    LedColor.fallYellow,
                ],
            },
        }

        self.__start_thread_for_group("all_beat", **all_beat)
        self.__start_thread_for_group("every_2nd_beat", **every_2nd_beat)

    def dual_beats_with_tatums(self, audio_analysis: SpotifyAudioAnalysis):
        self.groups = {}

        log.info("Starting dual beats.")

        self.create_group_of_every_nth(n=3, offset=0, group_name="all_beat")
        self.create_group_of_every_nth(
            n=3, offset=1, group_name="every_2nd_beat"
        )
        self.create_group_of_every_nth(n=3, offset=2, group_name="tatum")

        # Run on every beat
        all_beat = {
            "target": self.run_group_on_item,
            "args": [audio_analysis, "all_beat", 1],
            "kwargs": {
                "color_change_on": "beats",
                "item": "beats",
                "colors": [
                    Color(
                        255,
                        0,
                        0,
                    ),
                    Color(
                        255,
                        255,
                        255,
                    ),
                ],
            },
        }
        # Run on every second beat
        every_2nd_beat = {
            "target": self.run_group_on_item,
            "args": [audio_analysis, "every_2nd_beat", 2],
            "kwargs": {
                "item": "beats",
                "colors": [
                    LedColor.green,
                    LedColor.autumnOrange,
                    LedColor.brightViolet,
                    LedColor.fallYellow,
                ],
            },
        }

        # Run on every Tatum
        tatum = {
            "target": self.run_group_on_item,
            "args": [audio_analysis, "tatum", 1],
            "kwargs": {
                "item": "tatums",
                "colors": [
                    LedColor.brightViolet,
                ],
            },
        }

        self.__start_thread_for_group("all_beat", **all_beat)
        self.__start_thread_for_group("every_2nd_beat", **every_2nd_beat)
        self.__start_thread_for_group("tatum", **tatum)
