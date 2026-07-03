"""果园巡检演示时间轴。

该模块只处理“视频播放到哪个原始时间点时，应该模拟识别到果树”。
真正的 UDP 打包和发送仍然放在 udp_sender.py 中，避免主流程里混入太多演示逻辑。
"""


class PatrolTreeTimeline:
    """按照原视频时间点触发果树事件。"""

    def __init__(self, event_times, start_tree_id=1, match_tolerance=0.08):
        self.event_times = sorted(float(item) for item in event_times)
        self.next_tree_id = int(start_tree_id)
        self.match_tolerance = float(match_tolerance)
        self.last_time_by_traversal = {}
        self.triggered = set()

    def consume_event(self, playback_time, playback_direction=1, traversal_index=0):
        """如果当前播放位置越过了果树时间点，则返回一个新的果树事件。"""
        if playback_time is None or not self.event_times:
            return None

        current_time = float(playback_time)
        direction = 1 if int(playback_direction or 1) >= 0 else -1
        traversal = int(traversal_index or 0)
        state_key = (traversal, direction)
        previous_time = self.last_time_by_traversal.get(state_key)
        self.last_time_by_traversal[state_key] = current_time

        matched_time = self._match_event_time(previous_time, current_time, direction)
        if matched_time is None:
            return None

        event_key = (traversal, direction, matched_time)
        if event_key in self.triggered:
            return None
        self.triggered.add(event_key)

        left_tree_id = self.next_tree_id
        right_tree_id = self.next_tree_id + 1
        self.next_tree_id += 2
        if self.next_tree_id > 65535:
            self.next_tree_id = 1

        return {
            "left_tree_id": left_tree_id,
            "right_tree_id": right_tree_id,
            "tree_code": f"LID{left_tree_id:04d}/RID{right_tree_id:04d}",
            "event_time": matched_time,
            "playback_time": current_time,
            "direction": direction,
            "traversal_index": traversal,
        }

    def _match_event_time(self, previous_time, current_time, direction):
        """判断当前帧是否命中或跨过了某个事件点。"""
        if previous_time is None:
            for event_time in self.event_times:
                if abs(current_time - event_time) <= self.match_tolerance:
                    return event_time
            return None

        if direction >= 0:
            for event_time in self.event_times:
                if previous_time < event_time <= current_time:
                    return event_time
        else:
            for event_time in reversed(self.event_times):
                if current_time <= event_time < previous_time:
                    return event_time
        return None
