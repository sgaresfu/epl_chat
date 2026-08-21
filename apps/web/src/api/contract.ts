/**
 * Binds the hand-written types to the generated OpenAPI schema.
 *
 * `types.ts` exists for ergonomics -- `Fixture` reads better than
 * `components['schemas']['FixtureOut']` at every call site. But two
 * descriptions of the same shape is precisely the drift the brief warns about,
 * so this file asserts, at compile time, that each alias is mutually
 * assignable with the schema FastAPI actually publishes.
 *
 * If a Pydantic model changes and `npm run gen:api` is re-run, this file stops
 * compiling and CI fails. Nothing here emits any runtime code.
 */

import type { components } from './schema'
import type {
  AdminStatus,
  Club,
  Fixture,
  FixtureList,
  FplStandings,
  H2H,
  Leaderboard,
  Freshness,
  Home,
  LeagueTable,
  LocalTime,
  Me,
  Person,
  Predictions,
  ProjectedTable,
  Season,
  TableRow,
} from './types'

type Schemas = components['schemas']

/**
 * Compile-time proof that two types describe the same shape.
 *
 * `Exact` must resolve to `true` or `false`, never to `never`: `never extends
 * true` is vacuously true, so an assertion written against `never` silently
 * passes and the whole guard becomes decorative.
 */
type Exact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false

/**
 * Fails to compile unless `T` is exactly `true`.
 *
 * The constraint is what does the work. Computing `Exact<...>` into an unused
 * alias checks nothing at all -- TypeScript is happy to name a `false` type.
 */
type Assert<T extends true> = T

// Each line fails to compile if the hand-written alias and the generated
// schema have diverged in either direction.
type _Person = Assert<Exact<Person, Schemas['PersonOut']>>
type _Me = Assert<Exact<Me, Schemas['MeOut']>>
type _Club = Assert<Exact<Club, Schemas['ClubOut']>>
type _Freshness = Assert<Exact<Freshness, Schemas['Freshness']>>
type _LocalTime = Assert<Exact<LocalTime, Schemas['LocalTimeOut']>>
type _TableRow = Assert<Exact<TableRow, Schemas['TableRowOut']>>
type _LeagueTable = Assert<Exact<LeagueTable, Schemas['TableOut']>>
type _Projected = Assert<Exact<ProjectedTable, Schemas['ProjectedTableOut']>>
type _Fixture = Assert<Exact<Fixture, Schemas['FixtureOut']>>
type _FixtureList = Assert<Exact<FixtureList, Schemas['FixtureListOut']>>
type _Season = Assert<Exact<Season, Schemas['SeasonOut']>>
type _Home = Assert<Exact<Home, Schemas['HomeOut']>>
type _Predictions = Assert<Exact<Predictions, Schemas['PredictionsOut']>>
type _Admin = Assert<Exact<AdminStatus, Schemas['AdminStatusOut']>>
type _Fpl = Assert<Exact<FplStandings, Schemas['FplStandingsOut']>>
type _Lb = Assert<Exact<Leaderboard, Schemas['LeaderboardOut']>>
type _H2H = Assert<Exact<H2H, Schemas['H2HOut']>>

// Referenced so `noUnusedLocals` sees them as used. Every entry is `true` by
// construction; a drifted type makes its `Assert` fail to satisfy the constraint.
export type ContractHolds = [
  _Person, _Me, _Club, _Freshness, _LocalTime, _TableRow, _LeagueTable,
  _Projected, _Fixture, _FixtureList, _Season, _Home, _Predictions, _Admin, _Fpl, _Lb, _H2H,
]
