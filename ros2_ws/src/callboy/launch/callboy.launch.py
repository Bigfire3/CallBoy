from __future__ import annotations

from launch.actions import DeclareLaunchArgument, TimerAction
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "riva_server",
                default_value="localhost:50051",
                description="Riva Speech API gRPC endpoint, e.g. localhost:50051 or <container-ip>:50051",
            ),
            DeclareLaunchArgument(
                "riva_language_code",
                default_value="de-DE",
                description="ASR language code (e.g. de-DE, en-US)",
            ),
            Node(
                package="callboy",
                executable="callboy_riva_asr",
                name="riva_asr",
                output="screen",
                parameters=[
                    {
                        "server": LaunchConfiguration("riva_server"),
                        "language_code": LaunchConfiguration("riva_language_code"),
                        "sample_rate_hz": 16000,
                        "channels": 1,
                        "interim_results": True,
                        "print_interim": True,
                        "enable_automatic_punctuation": False,
                        "output_topic": "callboy/input_text",
                        "input_topic": "/g1/mics/pcm16",
                    }
                ],
            ),
            Node(
                package="callboy",
                executable="callboy_ollama_planner",
                name="ollama_planner",
                output="screen",
            ),
            TimerAction(
                period=1.0,
                actions=[
                    Node(
                        package="callboy",
                        executable="callboy_sdk2_executor",
                        name="sdk2_executor",
                        output="screen",
                    )
                ],
            ),
            TimerAction(
                period=2.0,
                actions=[
                    Node(
                        package="callboy",
                        executable="callboy_input_text",
                        name="input_text_publisher",
                        output="screen",
                    )
                ],
            ),
        ]
    )
