"""Computer vision for Chemputer"""

import cv2
import time
import os
import imutils
from skimage.metrics import structural_similarity
import numpy as np
from typing import Callable, Tuple

class SyringeBreakageDetector:
    """
    Syringe breakage detector.

    Args:
        template_folder (str): Folder containing templates matching
            inidividual syringes.
        log_folder (str): TODO: Description of log folder argument
        on_syringe_breakage (Callable): Callback function to be called when
            syringe breakage detected. Should take name of syringe template
            file as argument.
        tracker_type (str): csrt tracker is default for fast processing
        camera_id (str): streaming protocol address of the ip camera
    """

    # OpenCV object tracker implementations
    OPENCV_OBJECT_TRACKERS = {
        "csrt": cv2.legacy.TrackerCSRT_create,
        "kcf": cv2.legacy.TrackerKCF_create,
        "boosting": cv2.legacy.TrackerBoosting_create,
        "mil": cv2.legacy.TrackerMIL_create,
        "tld": cv2.legacy.TrackerTLD_create,
        "medianflow": cv2.legacy.TrackerMedianFlow_create,
        "mosse": cv2.legacy.TrackerMOSSE_create
    }

    #: Type of tracker to use for tracking regions of interest.
    tracker_type: str = 'csrt'

    #: Look for syringe breakages every x number of frames.
    process_frame_interval: int = 30

    def __init__(
        self,
        template_folder: str,
        log_folder: str,
        on_syringe_breakage: Callable = None,
        tracker_type: str = 'csrt',
        camera_id: str = None,
    ) -> None:
        self.template_folder = template_folder
        self.log_folder = log_folder
        self.on_syringe_breakage = on_syringe_breakage
        self.tracker_type = tracker_type
        self.camera_id = camera_id

        # Frame counter
        self.cv_framegrabber_count = 0

        # Trackers for all bounding boxes
        self.trackers = cv2.legacy.MultiTracker_create()

        # List to store all syringe bounding boxes.
        self.boxes = []

        #: Region of interest to detect changes in
        self.roi = []

        # Load all template file paths
        self.template_file_paths = [
            self.template_folder + f for f in os.listdir(self.template_folder)
            if (self.template_folder + f).endswith(".PNG")]

        #: Previous frame for comparing difference between current and previous
        #: frames.
        self.prev_frame = None

        #: List to all store all syringe breakages detected as
        #: ``(timestamp, template_file_name)`` tuples.
        self.events = []

    def find_bounding_boxes(self, frame: np.ndarray):
        """Takes a frame and finds the bounding boxes of all the syringes.
        Returns bounding boxes and store in :py:attr:`boxes` attribute.
        Templates must be made for every individual syringe being looked for.

        Args:
            frame (numpy array): current frame from the video stream

        Returns:
            boxes (List[[int]): list of bounding boxes for each syringe ROI.
        """
        # List to hold all template images
        template_data = []

        # Load all template images into template_data with edge detection.
        for template_file_path in self.template_file_paths:
            # Read image converting to grayscale (mode 0)
            template = cv2.imread(filename=template_file_path, flags=0)
            # Edge detection. After this template is masked image with
            # edges.
            template = cv2.Canny(image=template, threshold1=100,
                                 threshold2=200)

            template_data.append(template)

        # Loop over the images to find the template in
        for template in template_data:
            template_height, template_width = template.shape[:2]
            found = None
            # Loop over the scales of the image (zooming in / out)
            for scale in np.linspace(0.2, 1.0, 20)[::-1]:
                # Resize the image according to the scale, and keep track
                # of the ratio of the resizing
                resized_frame = imutils.resize(
                    frame, width=int(frame.shape[1] * scale))
                # Get ratio of original frame to resized frame.
                resize_ratio = frame.shape[1] / float(resized_frame.shape[1])
                # If the resized image is smaller than the template, then
                # break from the loop. Template is bigger than frame so no
                # point scaling further.
                if (resized_frame.shape[0] < template_height
                        or resized_frame.shape[1] < template_width):
                    break

                # Detect edges in the resized, grayscale frame image and
                # apply template matching to find the template in the
                # image.
                resized_frame_with_edges_detected = cv2.Canny(
                    image=resized_frame, threshold1=100, threshold2=200)

                # Match resized frame with template
                result = cv2.matchTemplate(
                    resized_frame_with_edges_detected, template,
                    cv2.TM_CCOEFF)

                # Get score of match and x, y coordinates of top left of
                # match box.
                _, match_score, _, match_top_left = cv2.minMaxLoc(result)

                # If no match has been found or this match has a better
                # score than  the previous match, replace the old match
                # with the new one.
                if found is None or match_score > found[0]:
                    found = (match_score, match_top_left, resize_ratio)

            # Calculate the bounding box based on the matched location and
            # resize ratio of the match.
            _, match_top_left, resize_ratio = found

            # Get bounding box top left coordinates
            bb_top_left_x, bb_top_left_y = (
                int(match_top_left[0] * resize_ratio),
                int(match_top_left[1] * resize_ratio)
            )
            # Get bounding box bottom right coordinates
            bb_bottom_right_x, bb_bottom_right_y = (
                int((match_top_left[0] + template_width) * resize_ratio),
                int((match_top_left[1] + template_height) * resize_ratio)
            )
            # Append bounding box
            self.boxes.append((
                bb_top_left_x,
                bb_top_left_y,
                bb_bottom_right_x - bb_top_left_x,
                bb_bottom_right_y - bb_top_left_y
            ))
        return self.boxes

        # Initialize a dictionary that maps strings to their corresponding
    def initialize_boxes(self, frame: np.ndarray):
        """Takes a current frame and find the bounding boxes

        Args:
            frame (numpy array): current frame from the video stream
        """
        # Select the bounding box of the object we want to track (make
        # sure you press ENTER or SPACE after selecting the ROI)
        # box = cv2.selectROI("Frame", frame, fromCenter=False,
        #     showCrosshair=True)
        self.find_bounding_boxes(frame)

        # Create a new object tracker for the bounding box and add trackers
        # for all bounding boxes to the multi-object tracker.
        tracker = self.OPENCV_OBJECT_TRACKERS[self.tracker_type]()
        for box in self.boxes:
            self.trackers.add(tracker, frame, box)

    def process_frame(self, frame: np.ndarray):
        """Takes current frame, after finding the bounding boxes for all the
        syringes, the state of the syringe is continously monitored for any
        breakage that may occur. Moreover, illumincation changes are also
        monitored to avoid false detection of syringe breakage.
        On detection of a syringe breakage event, a callable function is
        called [TODO halt chemputer] and current fame will be saved.

        Args:
            frame (numpy array): current frame from the video stream

        """
        if not self.boxes:
            self.initialize_boxes(frame)
            self.prev_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return
        original_frame = frame
        frame = frame.copy()

        # Get brightness of the frame and make sure brightness is consistent
        hsvImage = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        result = cv2.mean(hsvImage)
        image_brightness = int(result[2])

        # Perform a check of the mean brightness of an image
        # to include some degree of illumincatin invariance.
        # If the illumincation is not consistent, suggest for the
        # illuumincation to be adjusted
        if image_brightness < 103:

            # Display an alert message if the illumincation is below a
            # threshold
            font = cv2.FONT_HERSHEY_SIMPLEX
            text = "Critical Alert: Illumination adjustment needed"

            # get boundary of this text
            textsize = cv2.getTextSize(text, font, 1, 2)[0]

            # get coords based on boundary
            textX = int((original_frame.shape[1] - textsize[0]) / 2)
            textY = int((original_frame.shape[0] + textsize[1]) / 2)

            # add text centered on image
            cv2.putText(original_frame, text, (textX - 280, textY), font, 2,
                        (0, 0, 255), 2)
            cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)
            cv2.imshow("Frame", original_frame)
            cv2.waitKey(1)

            self.frameCount = -100
            return

        # Convert frame to grayscale
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Loop over the bounding boxes and draw then on the frame
        for i, box in enumerate(self.boxes):

            # Get name of template file associated with current bounding box
            template_file_name = os.path.splitext(
                os.path.basename(self.template_file_paths[i]))

            # Unpack position and dimensions of box
            x, y, w, h = [int(v) for v in box]

            # Define region of interest
            roi = [x, y, w, h]

            # Draw bounding box on video.
            cv2.rectangle(
                img=original_frame,
                pt1=(x, y),
                pt2=(x + w, y + h),
                color=(0, 255, 0),
                thickness=2)
            # Display which template file is being matched next to the
            # bounding box.
            cv2.putText(
                img=original_frame,
                text=template_file_name[0],
                org=(x, y - 10),
                fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                fontScale=0.9,
                color=(36, 255, 12),
                thickness=2)

            # After first frame has passed.
            if self.prev_frame is not None:

                # Check if syringe is broken
                if self.detect_change(self.prev_frame, frame, roi):

                    # Draw bounding box on video.
                    cv2.rectangle(
                        img=original_frame,
                        pt1=(x, y),
                        pt2=(x + w, y + h),
                        color=(0, 0, 255),
                        thickness=2)
                    # Display the syringe with anomaly in red bounding
                    # box on video.
                    cv2.putText(
                        img=original_frame,
                        text=template_file_name[0],
                        org=(x - 15, y),
                        fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                        fontScale=0.7,
                        color=(0, 0, 255),
                        thickness=2)
                    # Saving the current frame when syringe breaks
                    cv2.imwrite(
                        os.path.join(self.log_folder, 'halting_image.jpg'),
                        frame
                    )
                    # Prepare and display the alert message on the video
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    text = f'Critical Alert: {template_file_name[0]}\
 needs attention'

                    # get boundary of this text
                    textsize = cv2.getTextSize(text, font, 1, 2)[0]

                    # get coords based on boundary
                    textX = int((original_frame.shape[1] - textsize[0])
                                / 2)
                    textY = int((original_frame.shape[0] + textsize[1])
                                / 2)

                    # add text centered on image
                    cv2.putText(original_frame, text,
                                (textX - 280, textY - 120), font, 2,
                                (0, 0, 255), 2)

                    self.events.append((time.time(), template_file_name))

                    # Callback function when syringe breaks
                    if self.on_syringe_breakage:
                        self.on_syringe_breakage(template_file_name)

        self.prev_frame = frame
# =============================================================================
#         # Display the current frame
#         cv2.namedWindow("Frame", cv2.WINDOW_NORMAL)
#         cv2.imshow("Frame", original_frame)
#         cv2.waitKey(1)
# =============================================================================

    def detect_change(
        self,
        prev_frame: np.ndarray,
        current_frame: np.ndarray,
        roi: Tuple[float],
        threshold: float = 0.95
    ) -> bool:
        """Takes previous and current frames and detect if there has been a
        change in the region of interest (roi). The change detected is valid
        in the ROI of the two frames if it is above a threashold.

        Args:
            previous_frame (numpy array): approximately a second older frame
            current_frame (numpy array): current frame
            ROI (Tuple[float]): Bounding box coordinates
            threshold (float): predefined threshold obtained from experiments.

            Returns:
            bool: True or False.
        """
        x, y, w, h = roi
        score, diff = structural_similarity(
            prev_frame[y:y + h, x:x + w],
            current_frame[y:y + h, x:x + w],
            full=True,
            multichannel=True
        )
        diff = (diff * 255).astype("uint8")
        return score < threshold
