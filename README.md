OilLevelReader
==============

OpenCV based oil meter level reader for Webcam

Uses a webcam and openCV on a Raspberry PI for reading an analog dial meter of an home heating oil tank.
The angle of the needle is determined and converted to a percentage full for the tank

The number will be sent to home user via email notification. An email will be sent at 75%, 50%, 25%, 10%, and 5% intervals. Email will include image of dial as well.

This was forked from @techsavi and retrofitted to work with my setup.
