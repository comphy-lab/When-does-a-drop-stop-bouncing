#ifndef PARAMS_H
#define PARAMS_H

#include <errno.h>
#include <math.h>
#include <strings.h>

#include "parse_params.h"

static double param_double (const char * key, double fallback)
{
  const char * raw = params_get_raw(key);
  if (!raw || !raw[0])
    return fallback;

  char * end = NULL;
  errno = 0;
  double value = strtod(raw, &end);
  if (errno != 0 || end == raw || (end && *end != '\0')) {
    fprintf(ferr,
            "params warning: key '%s' in %s is not a valid double ('%s'); using %g\n",
            key, params_source_file(), raw, fallback);
    return fallback;
  }
  return value;
}

static int param_int (const char * key, int fallback)
{
  const char * raw = params_get_raw(key);
  if (!raw || !raw[0])
    return fallback;

  char * end = NULL;
  errno = 0;
  long value = strtol(raw, &end, 10);
  if (errno != 0 || end == raw || (end && *end != '\0')) {
    fprintf(ferr,
            "params warning: key '%s' in %s is not a valid integer ('%s'); using %d\n",
            key, params_source_file(), raw, fallback);
    return fallback;
  }
  return (int) value;
}

static int param_bool (const char * key, int fallback)
{
  const char * raw = params_get_raw(key);
  if (!raw || !raw[0])
    return fallback;

  if (!strcasecmp(raw, "1") || !strcasecmp(raw, "true") || !strcasecmp(raw, "yes") ||
      !strcasecmp(raw, "on"))
    return 1;
  if (!strcasecmp(raw, "0") || !strcasecmp(raw, "false") || !strcasecmp(raw, "no") ||
      !strcasecmp(raw, "off"))
    return 0;

  fprintf(ferr,
          "params warning: key '%s' in %s is not a valid boolean ('%s'); using %d\n",
          key, params_source_file(), raw, fallback);
  return fallback;
}

static const char * param_string (const char * key, const char * fallback)
{
  const char * raw = params_get_raw(key);
  return (raw && raw[0]) ? raw : fallback;
}

static double param_double_min (const char * key, double fallback, double min_value)
{
  double value = param_double(key, fallback);
  if (value < min_value) {
    fprintf(ferr,
            "params warning: key '%s' in %s is below %g; using %g\n",
            key, params_source_file(), min_value, fallback);
    return fallback;
  }
  return value;
}

static int param_int_min (const char * key, int fallback, int min_value)
{
  int value = param_int(key, fallback);
  if (value < min_value) {
    fprintf(ferr,
            "params warning: key '%s' in %s is below %d; using %d\n",
            key, params_source_file(), min_value, fallback);
    return fallback;
  }
  return value;
}

#endif
