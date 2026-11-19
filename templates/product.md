# Product map

<!-- Every feature of the product, decided once from the product spec, before any feature is built. The ux-designer
     writes it; the person approves it together with the design (/greenlight:approve design). Each feature is later
     built with /greenlight:feature, in build order, and keeps its id. `bdd gallery --check` checks this table: ids
     are FEAT-<number> and unique, every feature has a name and a one-line description, every dependency is a feature
     of this map, and a feature is built after the features it depends on. -->

| ID | Feature | Description | Depends on | Order |
|---|---|---|---|---|
