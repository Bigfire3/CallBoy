import os
from glob import glob

from setuptools import find_packages, setup

package_name = "callboy"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools", "faster-whisper"],
    zip_safe=True,
    maintainer="unitree",
    maintainer_email="unitree@example.com",
    description="ROS2 nodes: CLI input -> Ollama planning -> SDK2 command execution for Unitree G1.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "callboy_input_text = callboy.nodes.input_text_publisher:main",
            "callboy_ollama_planner = callboy.nodes.ollama_planner:main",
            "callboy_sdk2_executor = callboy.nodes.sdk2_executor_node:main",
            "callboy_udp_audio_topic = callboy.nodes.udp_audio_topic_publisher:main",
            "callboy_riva_asr = callboy.nodes.riva_asr_node:main",
            "callboy_whisper_asr = callboy.nodes.callboy_whisper_asr:main",
            "callboy_wav_audio_topic = callboy.nodes.wav_audio_topic_publisher:main",
        ],
    },
)
