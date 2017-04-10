import cv2
import numpy


class OpticalFlow(object):

    def __init__(self, trackrate, max_features, min_threshold, reverse=True):
        self._trackrate = trackrate
        self._max_features = max_features
        self._min_threshold = min_threshold
        self._reverse = reverse

        self._frame_count = 0

        self._prev_frame = None
        self._prev_features = None
        self._features = None

    def update_settings(self,
            trackrate=None, max_features=None, min_threshold=None, reverse=None):
        if trackrate is not None:
            self._trackrate = trackrate
        if max_features is not None:
            self._max_features = max_features
        if min_threshold is not None:
            self._min_threshold = min_threshold
        if reverse is not None:
            self._reverse = reverse

    def update(self, frame, emitter):
        self._frame_count += 1

        feat_status = None
        if self._prev_frame is not None:
            if self._features is None or self._frame_count % self._trackrate == 0:
                self._features = cv2.goodFeaturesToTrack(self._prev_frame, self._max_features, 0.005, 3.0)
            if self._features is not None:
                self._prev_features = self._features.copy()
                self._features, feat_status, err = cv2.calcOpticalFlowPyrLK(
                        self._prev_frame, frame, self._prev_features, self._features)
        self._prev_frame = frame.copy()

        # Apply force to particles using the current optical flow info.
        height = frame.shape[0]
        features = self._features if self._features is not None else []
        feat_status = feat_status if feat_status is not None else []
        for indx, (feat, status) in enumerate(zip(features, feat_status)):
            if not status:
                continue
            destination = feat[0][::-1]
            origin = self._prev_features[indx][0][::-1]  # XXX is there a guarantee that this indx exists?
            velocity = origin - destination if self._reverse else destination - origin
            norm = numpy.sqrt((velocity ** 2).sum())
            if norm / height > self._min_threshold:
                emitter.add_force(tuple(origin), tuple(velocity))
