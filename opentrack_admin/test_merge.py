"""Tests for track-event merge-group parsing (parse_event_merge_groups)."""

from datetime import time
from pathlib import Path

from opentrack_admin.events import (
    EventMergeGroup,
    EventSchedule,
    parse_event_merge_groups,
)

HEADER = "event_group_id,event_type,categories,venue,start_time,end_time,duration_minutes\n"


def _write(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "schedule_events.csv"
    path.write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return path


def test_track_row_with_two_categories_makes_a_merge_group(tmp_path):
    path = _write(tmp_path, '80m hekk_J15+G14_group,80m hekk,"G14,J15",track,17:15,17:20,5')

    groups = parse_event_merge_groups(path)

    assert len(groups) == 1
    group = groups[0]
    assert group.primary.search_term == "G14 80 meter hekk"
    assert [o.search_term for o in group.others] == ["J15 80 meter hekk"]
    # All members share the row's start time.
    assert {m.start_time.strftime("%H:%M") for m in group.members} == {"17:15"}


def test_three_category_track_row_keeps_first_as_primary(tmp_path):
    path = _write(tmp_path, '600m_11-14_group,600m,"G12,G13,G14",track,17:25,17:30,5')

    groups = parse_event_merge_groups(path)

    assert len(groups) == 1
    assert groups[0].primary.search_term == "G12 600 meter"
    assert [o.search_term for o in groups[0].others] == [
        "G13 600 meter",
        "G14 600 meter",
    ]


def test_field_rows_are_not_merged(tmp_path):
    path = _write(
        tmp_path,
        'Diskos_G14+J13+J12_group,Diskos,"G14,J12,J13",throwing_circle,17:00,17:20,20',
        'Lengde_G12+J12_group,Lengde,"G12,J12",jumping_pit,17:10,17:30,20',
    )

    assert parse_event_merge_groups(path) == []


def test_single_category_track_row_is_not_a_merge_group(tmp_path):
    path = _write(tmp_path, "60m hekk_G11_group,60m hekk,G11,track,17:00,17:05,5")

    assert parse_event_merge_groups(path) == []


def test_ball_throw_is_not_merged(tmp_path):
    # "Liten ball" (ball-throw, BT) is a field/throwing event, not a track heat.
    path = _write(
        tmp_path,
        'Liten ball_G-Rekrutt+J-Rekrutt_group,Liten ball,"G-Rekrutt,J-Rekrutt",javelin_area,17:00,17:06,6',
    )

    assert parse_event_merge_groups(path) == []


def _group(event: str, *categories: str) -> EventMergeGroup:
    members = [EventSchedule(category=c, event=event, start_time=time(17, 0)) for c in categories]
    return EventMergeGroup(primary=members[0], others=members[1:])


def test_merged_name_mixed_genders_age_range():
    # The motivating example: boys and girls across two ages.
    assert _group("200m", "G13", "J13", "G14", "J14").merged_name == "G/J 13-14 200 meter"


def test_merged_name_single_gender_age_range():
    assert _group("600m", "G12", "G13", "G14").merged_name == "G 12-14 600 meter"


def test_merged_name_mixed_genders_single_age():
    assert _group("400m", "G-Rekrutt", "J-Rekrutt").merged_name == "G/J 10 400 meter"


def test_merged_name_hurdles_mixed():
    assert (
        _group("60H", "G11", "G12", "J12", "G13").merged_name
        == "G/J 11-13 60 meter hekk"
    )


def test_merged_name_girls_only():
    assert _group("80H", "J14", "J15").merged_name == "J 14-15 80 meter hekk"


def test_categories_folding_to_same_event_collapse(tmp_path):
    # Masters fold to senior (KV45-49 -> KS), so a row pairing a masters bracket
    # with its senior pool is a single OpenTrack event, not a merge.
    path = _write(
        tmp_path,
        '200m_women_group,200m,"Kvinner Senior,Kvinner masters 45-49",track,17:30,17:35,5',
    )

    assert parse_event_merge_groups(path) == []
