-- ============================================================
-- AI-based Village Pond Planning System — Supabase schema
-- Run this once in your Supabase project's SQL editor
-- (Project -> SQL Editor -> New query -> paste -> Run)
-- ============================================================

-- Optional: enables true PostGIS geometry/geography types for future use.
-- Not required for the prototype (geometries are stored as GeoJSON in
-- JSONB columns below), but recommended if you later want spatial
-- queries (ST_Intersects, ST_Area, etc.) done in the database itself.
create extension if not exists postgis;

-- ------------------------------------------------------------
-- villages: one row per AOI a user has analyzed
-- ------------------------------------------------------------
create table if not exists villages (
  id            bigint generated always as identity primary key,
  name          text not null,
  min_lat       double precision not null,
  min_lon       double precision not null,
  max_lat       double precision not null,
  max_lon       double precision not null,
  created_at    timestamptz not null default now(),
  unique (name)
);

-- ------------------------------------------------------------
-- dem_cache: cached elevation raster + derived layers per village
-- (elevation / slope / flow_direction stored as JSONB arrays so the
--  backend can reconstruct numpy arrays without recomputation)
-- ------------------------------------------------------------
create table if not exists dem_cache (
  id                bigint generated always as identity primary key,
  village_id        bigint not null references villages(id) on delete cascade,
  source            text not null,
  resolution_m      double precision not null,
  elevation         jsonb not null,   -- 2D array of floats
  slope             jsonb,            -- 2D array of floats (% slope), cached after first compute
  flow_direction    jsonb,            -- 2D array of ints (D8 direction index), cached after first compute
  fetched_at        timestamptz not null default now(),
  unique (village_id)
);

-- ------------------------------------------------------------
-- candidate_sites: proposed pond locations per village
-- ------------------------------------------------------------
create table if not exists candidate_sites (
  id                  bigint generated always as identity primary key,
  village_id          bigint not null references villages(id) on delete cascade,
  grid_row            int not null,
  grid_col            int not null,
  lat                 double precision not null,
  lon                 double precision not null,
  slope_pct           double precision not null,
  land_type           text not null,
  suitability_score   double precision not null,
  created_at          timestamptz not null default now()
);

-- ------------------------------------------------------------
-- catchments: one delineated catchment per candidate site
-- ------------------------------------------------------------
create table if not exists catchments (
  id                  bigint generated always as identity primary key,
  candidate_site_id   bigint not null references candidate_sites(id) on delete cascade,
  area_ha             double precision not null,
  geojson             jsonb not null,   -- sampled boundary points as a GeoJSON Feature
  created_at          timestamptz not null default now(),
  unique (candidate_site_id)
);

-- ------------------------------------------------------------
-- rainfall_records: one cached rainfall summary per village
-- ------------------------------------------------------------
create table if not exists rainfall_records (
  id                  bigint generated always as identity primary key,
  village_id          bigint not null references villages(id) on delete cascade,
  source              text not null,
  years               int not null,
  mean_annual_mm      double precision not null,
  monthly_avg_mm      jsonb not null,   -- array of 12 floats
  fetched_at          timestamptz not null default now(),
  unique (village_id)
);

-- ------------------------------------------------------------
-- pond_recommendations: runoff estimate + sizing per candidate site
-- ------------------------------------------------------------
create table if not exists pond_recommendations (
  id                        bigint generated always as identity primary key,
  candidate_site_id         bigint not null references candidate_sites(id) on delete cascade,
  runoff_coefficient        double precision not null,
  mean_annual_rainfall_mm   double precision not null,
  annual_runoff_volume_m3   double precision not null,
  recommended_depth_m       double precision not null,
  recommended_surface_area_m2 double precision not null,
  storage_capacity_m3       double precision not null,
  capture_efficiency_pct    double precision not null,
  rank_score                double precision,
  justification             text,
  created_at                timestamptz not null default now(),
  unique (candidate_site_id)
);

-- Helpful indexes for lookups the API performs most often
create index if not exists idx_candidate_sites_village on candidate_sites(village_id);
create index if not exists idx_catchments_candidate on catchments(candidate_site_id);
create index if not exists idx_recommendations_candidate on pond_recommendations(candidate_site_id);

-- ------------------------------------------------------------
-- Row Level Security: disabled here since this backend uses the
-- service_role key server-side (never exposed to the browser).
-- If you later call Supabase directly from the frontend with the
-- anon key, enable RLS and add policies before doing so.
-- ------------------------------------------------------------
alter table villages disable row level security;
alter table dem_cache disable row level security;
alter table candidate_sites disable row level security;
alter table catchments disable row level security;
alter table rainfall_records disable row level security;
alter table pond_recommendations disable row level security;