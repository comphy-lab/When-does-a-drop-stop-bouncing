#include "parse_params.h"

static int param_string_equals_ignore_case (const char * lhs, const char * rhs)
{
  if (!lhs || !rhs)
    return 0;

  while (*lhs && *rhs) {
    char left = *lhs;
    char right = *rhs;
    if (left >= 'A' && left <= 'Z')
      left = (char) (left - 'A' + 'a');
    if (right >= 'A' && right <= 'Z')
      right = (char) (right - 'A' + 'a');
    if (left != right)
      return 0;
    lhs++;
    rhs++;
  }
  return (*lhs == '\0' && *rhs == '\0');
}

static double param_double (const char * key, double fallback)
{
  const char * raw = params_get_raw(key);
  if (!raw || !raw[0])
    return fallback;

  char * end = NULL;
  double value = strtod(raw, &end);
  if (end == raw || (end && *end != '\0')) {
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
  long value = strtol(raw, &end, 10);
  if (end == raw || (end && *end != '\0')) {
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

  if (param_string_equals_ignore_case(raw, "1") ||
      param_string_equals_ignore_case(raw, "true") ||
      param_string_equals_ignore_case(raw, "yes") ||
      param_string_equals_ignore_case(raw, "on"))
    return 1;
  if (param_string_equals_ignore_case(raw, "0") ||
      param_string_equals_ignore_case(raw, "false") ||
      param_string_equals_ignore_case(raw, "no") ||
      param_string_equals_ignore_case(raw, "off"))
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
