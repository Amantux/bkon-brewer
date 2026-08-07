# Recipes

One JSON file per recipe — the git-committable form of the brewer's recipe
library. Export from a running instance with the `bkon_brewer.export_recipes`
service; load them into an instance with `bkon_brewer.import_recipes`.

Files are deterministic (sorted keys, one recipe each), so editing a recipe is a
one-file diff and re-exporting an unchanged library leaves git clean. Edit them
by hand if you like — `import_recipes` validates each and skips (with a named
error) anything that would not brew.
