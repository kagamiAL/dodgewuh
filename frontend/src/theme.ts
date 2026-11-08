// Team colours shared by the screen renderer and phone UI so they always match
// (plans/teams/playcanvas-ryan.md: "Team colours and labels match phones").
// Plain hex so phone pages don't pull in PlayCanvas.
export const TEAM_HEX: Record<1 | 2, string> = {
  1: '#338cff',
  2: '#ff8c26',
}

export const TEAM_LABEL: Record<1 | 2, string> = {
  1: 'Team 1 (Blue)',
  2: 'Team 2 (Orange)',
}

export const TEAM_NAME: Record<1 | 2, string> = {
  1: 'Blue',
  2: 'Orange',
}
