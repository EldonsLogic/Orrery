// BRD-014: the five product stages shown by the Progress marks, mapped from the build state machine
// (contracts/build-states.md, BPL-020). Pure: a build state in, the index of the current stage out.
export const BUILD_STAGES = ['discover', 'blueprint', 'build', 'simulate', 'live'] as const;
export type BuildStage = (typeof BUILD_STAGES)[number];

/**
 * Index of the current stage (0 to 4), or 5 when every stage is complete (live).
 * No build state yet = discovery. A draft Blueprint = the Blueprint stage. Approved and team-reviewed builds wait
 * for or are in the build. Built in the sandbox = simulating. Simulated = going live. Unknown values fall back to 0.
 */
const CURRENT: Readonly<Record<string, number>> = {
  draft: 1,
  owner_approved: 2,
  team_reviewed: 2,
  built_in_sandbox: 3,
  simulated: 4,
  live: 5,
};

export const stageProgress = (buildState: string | null | undefined): number =>
  buildState && Object.hasOwn(CURRENT, buildState) ? CURRENT[buildState]! : 0;
