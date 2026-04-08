from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

import streamlit as st

from pickleball_tournament import TournamentScheduler


st.set_page_config(page_title="Pickleball Tournament", layout="centered")


def _parse_names(text: str) -> List[str]:
    # Reuse the same parsing rules as CLI: comma-separated, trimmed, ignore blanks.
    parts = [p.strip() for p in (text or "").split(",")]
    names = [p for p in parts if p]

    # De-dupe while preserving order.
    seen = set()
    out: List[str] = []
    for n in names:
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _ensure_state() -> None:
    if "scheduler" not in st.session_state:
        st.session_state.scheduler = None
    if "history" not in st.session_state:
        st.session_state.history = []
    if "last_error" not in st.session_state:
        st.session_state.last_error = None
    if "request_next_round" not in st.session_state:
        st.session_state.request_next_round = False


def _format_team(team) -> str:
    return f"{team[0]} + {team[1]}"


def _get_scheduler() -> Optional[TournamentScheduler]:
    return st.session_state.scheduler


_ensure_state()

st.title("Pickleball Tournament Scheduler")

st.caption("Share this page’s URL to open it on any phone.")

with st.expander("Setup", expanded=st.session_state.get("scheduler") is None):
    initial_players_text = st.text_area(
        "Players (comma-separated)",
        value=st.session_state.get("initial_players_text", ""),
        placeholder="Alice,Bob,Charlie,Denise,...",
        height=120,
    )
    st.session_state.initial_players_text = initial_players_text

    courts = st.number_input("Courts", min_value=1, max_value=3, value=3, step=1)

    seed_enabled = st.checkbox("Use seed", value=st.session_state.get("seed_enabled", False))
    seed = st.number_input(
        "Seed",
        min_value=0,
        max_value=2**31 - 1,
        value=st.session_state.get("seed", 0),
        step=1,
        disabled=not seed_enabled,
    )
    st.session_state.seed_enabled = seed_enabled
    st.session_state.seed = seed

    start_clicked = st.button("Start / Reset", use_container_width=True)

st.divider()

if start_clicked:
    names = _parse_names(initial_players_text)
    if len(names) < 4:
        st.session_state.last_error = "Need at least 4 players to start."
    else:
        st.session_state.scheduler = TournamentScheduler(
            names,
            courts=int(courts),
            seed=int(seed) if seed_enabled else None,
        )
        st.session_state.history = []
        st.session_state.last_error = None

scheduler = _get_scheduler()

if scheduler is None:
    st.info("Open Setup, enter players, then click Start / Reset.")
    if st.session_state.last_error:
        st.error(st.session_state.last_error)
    st.stop()

next_clicked_main = st.button("Next round", use_container_width=True, key="next_round_main")
if next_clicked_main:
    st.session_state.request_next_round = True

st.subheader("Attendance")
present_now = scheduler.present_players()
all_players = sorted(list(scheduler.players.keys()), key=str.lower)

selected_present = st.multiselect(
    "Present players",
    options=all_players,
    default=present_now,
)

# Apply presence settings.
selected_set = set(selected_present)
for name in all_players:
    scheduler.set_present(name, name in selected_set)

st.subheader("Late arrivals")
late_text = st.text_input("Add players (comma-separated)", value="")
add_clicked = st.button("Add", use_container_width=False)
if add_clicked:
    new_names = _parse_names(late_text)
    for n in new_names:
        scheduler.add_player(n)
    st.session_state.last_error = None
    st.rerun()

if st.session_state.request_next_round:
    st.session_state.request_next_round = False
    schedule = scheduler.schedule_next_round()
    if schedule is None:
        st.session_state.last_error = (
            "No valid schedule found (not enough players present, or all possible partnerships are exhausted)."
        )
    else:
        st.session_state.history.append(asdict(schedule))
        st.session_state.last_error = None

if st.session_state.last_error:
    st.error(st.session_state.last_error)

st.subheader("Current status")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Players present", len(scheduler.present_players()))
with col2:
    st.metric("Courts", scheduler.courts)
with col3:
    st.metric("Rounds scheduled", len(st.session_state.history))

st.subheader("Latest round")
if not st.session_state.history:
    st.write("No rounds scheduled yet.")
else:
    last = st.session_state.history[-1]
    # last is a dict version of RoundSchedule
    rows = []
    for idx, match in enumerate(last["matches"], start=1):
        (t1, t2) = match
        rows.append({"Court": idx, "Team 1": _format_team(tuple(t1)), "Team 2": _format_team(tuple(t2))})
    st.table(rows)

    sitting = last.get("sitting_out") or []
    if sitting:
        st.write("Sitting out:", ", ".join(sitting))

    st.subheader("Enter results")
    if last.get("results") is not None:
        st.success("Results already saved for this round.")
    else:
        winners: List[int] = []
        for idx, match in enumerate(last["matches"], start=1):
            (t1, t2) = match
            team1 = _format_team(tuple(t1))
            team2 = _format_team(tuple(t2))
            choice = st.radio(
                f"Court {idx} winner",
                options=[team1, team2],
                horizontal=True,
                key=f"winner_round_{last['round_number']}_court_{idx}",
            )
            winners.append(0 if choice == team1 else 1)

        save = st.button("Save results", use_container_width=True)
        if save:
            for (team1, team2), w in zip(last["matches"], winners, strict=True):
                if w == 0:
                    scheduler.record_match_result(winning_team=tuple(team1), losing_team=tuple(team2))
                else:
                    scheduler.record_match_result(winning_team=tuple(team2), losing_team=tuple(team1))
            last["results"] = winners
            st.success("Saved.")
            st.rerun()

    next_clicked_near_results = st.button(
        "Next round",
        use_container_width=True,
        key="next_round_near_results",
    )
    if next_clicked_near_results:
        st.session_state.request_next_round = True
        st.rerun()

st.subheader("Leaderboard")
leader_rows = []
for name, state in scheduler.players.items():
    leader_rows.append(
        {
            "Player": name,
            "Wins": state.wins,
            "Losses": state.losses,
            "Played": state.games_played,
            "Present": "Yes" if state.present else "No",
        }
    )
leader_rows.sort(key=lambda r: (-r["Wins"], r["Losses"], r["Player"].lower()))
st.table(leader_rows)

st.subheader("History")
if st.session_state.history:
    for item in reversed(st.session_state.history):
        st.write(f"Round {item['round_number']}")
        rows = []
        for idx, match in enumerate(item["matches"], start=1):
            (t1, t2) = match
            rows.append({"Court": idx, "Team 1": _format_team(tuple(t1)), "Team 2": _format_team(tuple(t2))})
        st.table(rows)
        sitting = item.get("sitting_out") or []
        if sitting:
            st.caption("Sitting out: " + ", ".join(sitting))
        st.divider()
