/**
# Low-Level Parameter Parser

Shared header-only parser for `key=value` runtime configuration files.

## Responsibilities

- load a parameter file selected from `argv`
- trim whitespace and strip inline `#` comments
- store the last value seen for repeated keys
- expose raw string lookups for the typed accessors in [`params.h`](params.h)

This header intentionally keeps the implementation small so simulation sources
can include it directly without linking an extra object file.
*/
#ifndef PARAMS_MAX_ENTRIES
#define PARAMS_MAX_ENTRIES 256
#endif

#ifndef PARAMS_KEY_SIZE
#define PARAMS_KEY_SIZE 64
#endif

#ifndef PARAMS_VALUE_SIZE
#define PARAMS_VALUE_SIZE 256
#endif

typedef struct {
  char key[PARAMS_KEY_SIZE];
  char value[PARAMS_VALUE_SIZE];
} param_entry_t;

static param_entry_t g_param_entries[PARAMS_MAX_ENTRIES];
static int g_param_entry_count = 0;
static char g_param_source[PARAMS_VALUE_SIZE] = "case.params";

/**
### params_is_space()

Returns non-zero when `c` is any ASCII whitespace character handled by the
parser.
*/
static int params_is_space (char c)
{
  return (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v');
}

/**
### params_trim_inplace()

Removes leading and trailing whitespace from `text` in place.
*/
static void params_trim_inplace (char * text)
{
  if (!text)
    return;

  char * start = text;
  while (*start && params_is_space(*start))
    start++;

  char * end = start + strlen(start);
  while (end > start && params_is_space(*(end - 1)))
    end--;

  size_t length = (size_t) (end - start);
  if (start != text)
    memmove(text, start, length);
  text[length] = '\0';
}

/**
### params_strip_inline_comment()

Truncates `text` at the first `#` marker and trims any surrounding whitespace.
*/
static void params_strip_inline_comment (char * text)
{
  if (!text)
    return;

  for (char * cursor = text; *cursor; cursor++) {
    if (*cursor == '#') {
      *cursor = '\0';
      break;
    }
  }
  params_trim_inplace(text);
}

/**
### params_store_entry()

Stores or updates a parsed `key=value` pair in the static parameter table.
*/
static void params_store_entry (const char * key, const char * value)
{
  for (int i = 0; i < g_param_entry_count; i++) {
    if (strcmp(g_param_entries[i].key, key) == 0) {
      snprintf(g_param_entries[i].value, PARAMS_VALUE_SIZE, "%s", value);
      return;
    }
  }

  if (g_param_entry_count >= PARAMS_MAX_ENTRIES) {
    fprintf(ferr, "params warning: too many entries in %s, ignoring key '%s'\n",
            g_param_source, key);
    return;
  }

  snprintf(g_param_entries[g_param_entry_count].key, PARAMS_KEY_SIZE, "%s", key);
  snprintf(g_param_entries[g_param_entry_count].value, PARAMS_VALUE_SIZE, "%s", value);
  g_param_entry_count++;
}

/**
### params_reset()

Clears all stored entries before loading a new parameter file.
*/
static void params_reset (void)
{
  g_param_entry_count = 0;
  g_param_source[0] = '\0';
}

/**
### params_load_file()

Parses `filename` into the static lookup table.

#### Returns

- `1` when the file was opened and parsed
- `0` when the file could not be opened
*/
static int params_load_file (const char * filename)
{
  FILE * fp = fopen(filename, "r");
  if (!fp) {
    fprintf(ferr, "params error: could not open '%s'\n", filename);
    return 0;
  }

  params_reset();
  snprintf(g_param_source, PARAMS_VALUE_SIZE, "%s", filename);

  char line[512];
  int line_number = 0;
  while (fgets(line, sizeof(line), fp)) {
    line_number++;
    params_strip_inline_comment(line);
    if (!line[0])
      continue;

    char * equals = strchr(line, '=');
    if (!equals) {
      fprintf(ferr, "params warning: ignoring malformed line %d in %s\n",
              line_number, filename);
      continue;
    }

    *equals = '\0';
    char * key = line;
    char * value = equals + 1;
    params_trim_inplace(key);
    params_trim_inplace(value);

    if (!key[0]) {
      fprintf(ferr, "params warning: ignoring empty key on line %d in %s\n",
              line_number, filename);
      continue;
    }

    params_store_entry(key, value);
  }

  fclose(fp);
  return 1;
}

/**
### params_init_from_argv()

Loads the parameter file provided as `argv[1]`, or falls back to
`case.params` when no explicit filename is passed.
*/
static int params_init_from_argv (int argc, char const * argv[])
{
  const char * filename = (argc > 1 && argv[1] && argv[1][0]) ? argv[1] : "case.params";
  return params_load_file(filename);
}

/**
### params_get_raw()

Looks up the raw string value associated with `key`.
*/
static const char * params_get_raw (const char * key)
{
  for (int i = 0; i < g_param_entry_count; i++)
    if (strcmp(g_param_entries[i].key, key) == 0)
      return g_param_entries[i].value;
  return NULL;
}

/**
### params_source_file()

Returns the name of the parameter file most recently loaded.
*/
static const char * params_source_file (void)
{
  return g_param_source;
}
