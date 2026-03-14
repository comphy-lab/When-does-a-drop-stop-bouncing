#ifndef PARSE_PARAMS_H
#define PARSE_PARAMS_H

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static void params_trim_inplace (char * text)
{
  if (!text)
    return;

  char * start = text;
  while (*start && isspace((unsigned char) *start))
    start++;

  char * end = start + strlen(start);
  while (end > start && isspace((unsigned char) *(end - 1)))
    end--;

  size_t length = (size_t) (end - start);
  if (start != text)
    memmove(text, start, length);
  text[length] = '\0';
}

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

static void params_reset (void)
{
  g_param_entry_count = 0;
  g_param_source[0] = '\0';
}

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

static int params_init_from_argv (int argc, char const * argv[])
{
  const char * filename = (argc > 1 && argv[1] && argv[1][0]) ? argv[1] : "case.params";
  return params_load_file(filename);
}

static const char * params_get_raw (const char * key)
{
  for (int i = 0; i < g_param_entry_count; i++)
    if (strcmp(g_param_entries[i].key, key) == 0)
      return g_param_entries[i].value;
  return NULL;
}

static const char * params_source_file (void)
{
  return g_param_source;
}

#endif
