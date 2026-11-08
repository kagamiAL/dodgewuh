"""Coordinator-only history writes; callers hold the room row lock."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from app.db.models import AllocationRecord, AssignmentRecord, MatchRecord, ResultRecord


class HistoryRepository:
    def __init__(self, db):
        self.db = db

    def end(self, room_id, reason):
        now = datetime.now(timezone.utc)
        allocation = self.db.scalar(select(AllocationRecord).where(AllocationRecord.room_id == room_id))
        if allocation and allocation.ended_at is None:
            allocation.ended_at, allocation.reason = now, reason
            for match in self.db.scalars(select(MatchRecord).where(
                    MatchRecord.allocation_id == allocation.id, MatchRecord.status == 'active')):
                match.status, match.ended_at, match.reason = 'aborted', now, reason

    def report(self, allocation, seq, state):
        if seq <= allocation.report_seq:
            return
        if seq != allocation.report_seq + 1:
            raise ValueError('History report sequence gap')
        now = datetime.now(timezone.utc)
        version = state['assignment_version']
        existing = list(self.db.scalars(select(AssignmentRecord).where(
            AssignmentRecord.allocation_id == allocation.id, AssignmentRecord.version == version)))
        if not existing:
            for a in state['assignments']:
                self.db.add(AssignmentRecord(allocation_id=allocation.id, version=version,
                    member_id=UUID(a['member_id']), team=a['team'], role=a['role'], recorded_at=now))
        match = self.db.scalar(select(MatchRecord).where(MatchRecord.allocation_id == allocation.id)
                               .order_by(MatchRecord.ordinal.desc()).limit(1))
        phase = state['phase']
        if phase in ('countdown', 'active') and (match is None or match.status != 'active'):
            match = MatchRecord(allocation_id=allocation.id, ordinal=match.ordinal + 1 if match else 1,
                                started_at=now, status='active')
            self.db.add(match)
            self.db.flush()
        if match and match.status == 'active' and phase in ('lobby', 'match_end'):
            match.ended_at = now
            if phase == 'match_end':
                if state['winner'] not in (1, 2, None):
                    raise ValueError('Completed match has an invalid winner')
                match.status = 'completed'
                self.db.add(ResultRecord(match_id=match.id, winner=state['winner'],
                    team1=state['score']['t1'], team2=state['score']['t2'], recorded_at=now))
            else:
                match.status, match.reason = 'aborted', 'reset_or_device_loss'
        allocation.report_seq = seq
