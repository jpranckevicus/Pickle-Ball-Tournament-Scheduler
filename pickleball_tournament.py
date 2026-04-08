from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple


PlayerName = str
Team = Tuple[PlayerName, PlayerName]
Match = Tuple[Team, Team]


@dataclass
class PlayerState:
    name: PlayerName
    present: bool = True
    games_played: int = 0
    last_round_played: int = -1
    wins: int = 0
    losses: int = 0


@dataclass
class RoundSchedule:
    round_number: int
    matches: List[Match]
    sitting_out: List[PlayerName]
    # Optional: for each match, 0 means team1 won, 1 means team2 won.
    results: Optional[List[int]] = None


class TournamentScheduler:
    def __init__(
        self,
        players: Iterable[PlayerName],
        *,
        courts: int = 3,
        seed: Optional[int] = None,
    ) -> None:
        self.courts = courts
        self.random = random.Random(seed)

        self.players: Dict[PlayerName, PlayerState] = {}
        for name in players:
            self.add_player(name)

        # Tracks partnerships that have already happened.
        self.partner_history: Set[FrozenSet[PlayerName]] = set()

        self.round_number = 0

    def add_player(self, name: PlayerName) -> None:
        name = name.strip()
        if not name:
            return
        if name in self.players:
            self.players[name].present = True
            return
        self.players[name] = PlayerState(name=name, present=True)

    def set_present(self, name: PlayerName, present: bool) -> None:
        if name not in self.players:
            self.players[name] = PlayerState(name=name, present=present)
        else:
            self.players[name].present = present

    def present_players(self) -> List[PlayerName]:
        return [p.name for p in self.players.values() if p.present]

    def _can_partner(self, a: PlayerName, b: PlayerName) -> bool:
        if a == b:
            return False
        return frozenset((a, b)) not in self.partner_history

    def _fairness_key(self, name: PlayerName) -> Tuple[int, int, str]:
        p = self.players[name]
        # Least games first; if tied, prefer those who haven't played recently.
        # (older last_round_played => smaller => higher priority)
        return (p.games_played, p.last_round_played, p.name.lower())

    def _choose_players_for_round(self, candidates: Sequence[PlayerName]) -> List[PlayerName]:
        """Choose up to 12 players (or fewer), divisible by 4."""
        max_players = min(4 * self.courts, len(candidates))
        max_players = (max_players // 4) * 4
        if max_players < 4:
            return []

        # Sort by fairness; we will pick from the head, but allow a little mixing
        # to avoid dead-ends when partnerships are constrained.
        ordered = sorted(candidates, key=self._fairness_key)

        # Use a small buffer so we can swap players in/out if matching fails.
        buffer_size = min(len(ordered), max_players + 6)
        pool = ordered[:buffer_size]

        # Start with the most fair selection.
        selection = pool[:max_players]
        return selection

    def _find_matching(self, players: Sequence[PlayerName]) -> Optional[List[Team]]:
        """Return teams (pairs) covering all players, or None if impossible."""
        remaining: Set[PlayerName] = set(players)

        allowed: Dict[PlayerName, List[PlayerName]] = {
            p: [q for q in players if q != p and self._can_partner(p, q)] for p in players
        }

        # Shuffle each adjacency list for variety (seeded).
        for p in players:
            self.random.shuffle(allowed[p])

        teams: List[Team] = []

        def backtrack() -> bool:
            if not remaining:
                return True

            # Pick the player with the fewest available partners (MRV heuristic).
            p = min(
                remaining,
                key=lambda x: sum(1 for q in allowed[x] if q in remaining),
            )

            options = [q for q in allowed[p] if q in remaining]
            if not options:
                return False

            for q in options:
                remaining.remove(p)
                remaining.remove(q)
                teams.append((p, q) if p < q else (q, p))

                if backtrack():
                    return True

                teams.pop()
                remaining.add(p)
                remaining.add(q)

            return False

        ok = backtrack()
        if not ok:
            return None
        return teams

    def _pair_teams_into_matches(self, teams: List[Team]) -> List[Match]:
        teams = teams[:]
        self.random.shuffle(teams)
        matches: List[Match] = []
        for i in range(0, len(teams), 2):
            matches.append((teams[i], teams[i + 1]))
        return matches

    def schedule_next_round(self, *, max_attempts: int = 200) -> Optional[RoundSchedule]:
        self.round_number += 1

        present = self.present_players()
        if len(present) < 4:
            return None

        base_candidates = sorted(present, key=self._fairness_key)

        # We may need to reduce courts if constraints are tight.
        for courts_to_try in range(self.courts, 0, -1):
            players_needed = 4 * courts_to_try
            if len(base_candidates) < players_needed:
                continue

            # Create a pool that includes a buffer beyond what we need.
            buffer = min(len(base_candidates), players_needed + 8)
            pool = base_candidates[:buffer]

            for attempt in range(max_attempts):
                # Start from the fairest set, then do a few random swaps
                # with the buffer to escape dead-ends.
                selected = pool[:players_needed]
                extras = pool[players_needed:]

                # Number of swaps increases over attempts.
                max_swaps = min(len(extras), 1 + attempt // 25)
                swaps = 0 if not extras else self.random.randint(0, max_swaps)

                if swaps:
                    selected = selected[:]
                    extras = extras[:]
                    for _ in range(swaps):
                        out_idx = self.random.randrange(len(selected))
                        in_idx = self.random.randrange(len(extras))
                        selected[out_idx], extras[in_idx] = extras[in_idx], selected[out_idx]

                matching = self._find_matching(selected)
                if matching is None:
                    continue

                matches = self._pair_teams_into_matches(matching)
                # Only schedule the number of courts we decided.
                matches = matches[:courts_to_try]

                scheduled_players = {p for team in matching for p in team}
                sitting_out = sorted(
                    [p for p in present if p not in scheduled_players],
                    key=self._fairness_key,
                )

                # Update history/state.
                for a, b in matching:
                    self.partner_history.add(frozenset((a, b)))

                for name in scheduled_players:
                    st = self.players[name]
                    st.games_played += 1
                    st.last_round_played = self.round_number

                return RoundSchedule(
                    round_number=self.round_number,
                    matches=matches,
                    sitting_out=sitting_out,
                    results=None,
                )

        # Could not schedule anything without violating constraints.
        return None

    def record_match_result(self, *, winning_team: Team, losing_team: Team) -> None:
        """Record a win for each player in winning_team and a loss for each player in losing_team."""
        for name in winning_team:
            if name not in self.players:
                self.players[name] = PlayerState(name=name)
            self.players[name].wins += 1

        for name in losing_team:
            if name not in self.players:
                self.players[name] = PlayerState(name=name)
            self.players[name].losses += 1

    def record_round_results(self, schedule: RoundSchedule, winners: Sequence[int]) -> None:
        """Persist results for a scheduled round.

        winners: list of ints with length == len(schedule.matches).
          - 0 => team1 won
          - 1 => team2 won
        """
        if len(winners) != len(schedule.matches):
            raise ValueError("winners must have one entry per match")
        if schedule.results is not None:
            raise ValueError("results already recorded for this round")

        normalized: List[int] = []
        for w in winners:
            if w not in (0, 1):
                raise ValueError("winner must be 0 (team1) or 1 (team2)")
            normalized.append(int(w))

        for (team1, team2), w in zip(schedule.matches, normalized, strict=True):
            if w == 0:
                self.record_match_result(winning_team=team1, losing_team=team2)
            else:
                self.record_match_result(winning_team=team2, losing_team=team1)

        schedule.results = normalized


def _parse_names_csv(text: str) -> List[str]:
    parts = [p.strip() for p in text.split(",")]
    return [p for p in parts if p]


def _load_players_from_file(path: str) -> List[str]:
    names: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Allow either one name per line OR comma-separated.
            if "," in line:
                names.extend(_parse_names_csv(line))
            else:
                names.append(line)
    # De-dupe while preserving order.
    seen: Set[str] = set()
    out: List[str] = []
    for n in names:
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _format_team(team: Team) -> str:
    return f"{team[0]} + {team[1]}"


def print_round(schedule: RoundSchedule) -> None:
    print(f"\n=== Round {schedule.round_number} ===")
    for i, match in enumerate(schedule.matches, start=1):
        (t1, t2) = match
        print(f"Court {i}:  {_format_team(t1)}  vs  {_format_team(t2)}")
    if schedule.sitting_out:
        print("Sitting out:", ", ".join(schedule.sitting_out))


HELP_INTERACTIVE = """
Interactive commands:
  add NAME1,NAME2,...   Add late arrivals (they become present immediately)
  absent NAME1,...      Mark players as absent (won't be scheduled)
  present NAME1,...     Mark players as present
  next                  Schedule the next round
  quit                  Exit
Notes:
  - Only the "no repeat partners" rule is enforced.
  - Max 3 courts => 12 players per round.
""".strip()


def interactive_loop(scheduler: TournamentScheduler) -> int:
    print(HELP_INTERACTIVE)
    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return 0

        if not raw:
            continue

        cmd, *rest = raw.split(" ", 1)
        args = rest[0] if rest else ""
        cmd = cmd.lower()

        if cmd in {"quit", "exit"}:
            return 0

        if cmd == "help":
            print(HELP_INTERACTIVE)
            continue

        if cmd == "add":
            for name in _parse_names_csv(args):
                scheduler.add_player(name)
            print(f"Present players: {len(scheduler.present_players())}")
            continue

        if cmd in {"absent", "present"}:
            present_value = cmd == "present"
            for name in _parse_names_csv(args):
                scheduler.set_present(name, present_value)
            print(f"Present players: {len(scheduler.present_players())}")
            continue

        if cmd == "next":
            schedule = scheduler.schedule_next_round()
            if schedule is None:
                print("\nNo valid schedule found (not enough players or partnerships are exhausted).")
                return 1
            print_round(schedule)
            continue

        print("Unknown command. Type 'help' for options.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pickleball doubles scheduler (3 courts max) enforcing: "
            "no repeat partners. Supports late arrivals via interactive mode."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--players", help="Comma-separated player names")
    group.add_argument("--players-file", help="Text file with player names")
    parser.add_argument("--courts", type=int, default=3, help="Number of courts (default: 3)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument(
        "--rounds",
        type=int,
        default=0,
        help="If >0, auto-generate this many rounds non-interactively",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode (supports adding late arrivals)",
    )

    args = parser.parse_args(argv)

    if args.players_file:
        names = _load_players_from_file(args.players_file)
    else:
        names = _parse_names_csv(args.players or "")

    if len(names) < 4:
        print("Need at least 4 players to schedule a match.")
        return 2

    scheduler = TournamentScheduler(names, courts=args.courts, seed=args.seed)

    if args.interactive:
        return interactive_loop(scheduler)

    if args.rounds and args.rounds > 0:
        for _ in range(args.rounds):
            schedule = scheduler.schedule_next_round()
            if schedule is None:
                print("\nStopped: no valid schedule found.")
                return 1
            print_round(schedule)
        return 0

    # Default: single round
    schedule = scheduler.schedule_next_round()
    if schedule is None:
        print("No valid schedule found.")
        return 1
    print_round(schedule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
