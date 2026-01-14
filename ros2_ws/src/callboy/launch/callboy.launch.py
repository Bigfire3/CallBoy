from __future__ import annotations

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            Node(
                package="callboy",
                executable="callboy_ollama_planner",
                name="ollama_planner",
                output="screen",
            ),
            Node(
                package="callboy",
                executable="callboy_sdk2_executor",
                name="sdk2_executor",
                output="screen",
            ),
            Node(
                package="callboy",
                executable="callboy_input_text",
                name="input_text_publisher",
                output="screen",
            ),
        ]
    )
