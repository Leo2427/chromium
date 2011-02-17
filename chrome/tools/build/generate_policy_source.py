#!/usr/bin/python
# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''python %prog [options] platform template

platform specifies which platform source is being generated for
  and can be one of (win, mac, linux).
template is the path to a .json policy template file.'''

from __future__ import with_statement
from optparse import OptionParser
import sys;


CHROME_SUBKEY = 'SOFTWARE\\\\Policies\\\\Google\\\\Chrome';
CHROMIUM_SUBKEY = 'SOFTWARE\\\\Policies\\\\Chromium';


def main():
  parser = OptionParser(usage=__doc__);
  parser.add_option("--pch", "--policy-constants-header", dest="header_path",
                    help="generate header file of policy constants",
                    metavar="FILE");
  parser.add_option("--pcc", "--policy-constants-source", dest="source_path",
                    help="generate source file of policy constants",
                    metavar="FILE");
  parser.add_option("--pth", "--policy-type-header", dest="type_path",
                    help="generate header file for policy type enumeration",
                    metavar="FILE");
  parser.add_option("--ppb", "--policy-protobuf", dest="proto_path",
                    help="generate cloud policy protobuf file",
                    metavar="FILE");
  parser.add_option("--ppd", "--protobuf-decoder", dest="decoder_path",
                    help="generate C++ code decoding the policy protobuf",
                    metavar="FILE");

  (opts, args) = parser.parse_args();

  if len(args) < 2 or len(args) > 2:
    print "exactly one platform and input file must be specified."
    parser.print_help()
    sys.exit(2)
  template_file_contents = _LoadJSONFile(args[1]);
  if opts.header_path is not None:
    _WritePolicyConstantHeader(template_file_contents, args, opts);
  if opts.source_path is not None:
    _WritePolicyConstantSource(template_file_contents, args, opts);
  if opts.type_path is not None:
    _WritePolicyTypeEnumerationHeader(template_file_contents, args, opts);
  if opts.proto_path is not None:
    _WriteProtobuf(template_file_contents, args, opts.proto_path)
  if opts.decoder_path is not None:
    _WriteProtobufParser(template_file_contents, args, opts.decoder_path)


#------------------ shared helpers ---------------------------------#
def _OutputGeneratedWarningForC(f, template_file_path):
    f.write('//\n'
            '// DO NOT MODIFY THIS FILE DIRECTLY!\n'
            '// IT IS GENERATED BY generate_policy_source.py\n'
            '// FROM ' + template_file_path + '\n'
            '//\n\n')


def _GetPolicyNameList(template_file_contents):
  policy_names = [];
  for policy in template_file_contents['policy_definitions']:
    if policy['type'] == 'group':
      for sub_policy in policy['policies']:
        policy_names.append(sub_policy['name'])
    else:
      policy_names.append(policy['name'])
  policy_names.sort()
  return policy_names


def _LoadJSONFile(json_file):
  with open(json_file, "r") as f:
    text = f.read()
  return eval(text)


#------------------ policy constants header ------------------------#
def _WritePolicyConstantHeader(template_file_contents, args, opts):
  platform = args[0];
  with open(opts.header_path, "w") as f:
    _OutputGeneratedWarningForC(f, args[1])
    f.write('#ifndef CHROME_COMMON_POLICY_CONSTANTS_H_\n'
            '#define CHROME_COMMON_POLICY_CONSTANTS_H_\n'
            '#pragma once\n'
            '\n'
            'namespace policy {\n\n')
    if platform == "win":
      f.write('// The windows registry path where policy configuration '
              'resides.\nextern const wchar_t kRegistrySubKey[];\n\n')
    f.write('// Key names for the policy settings.\n'
            'namespace key {\n\n')
    for policy_name in _GetPolicyNameList(template_file_contents):
      f.write('extern const char k' + policy_name + '[];\n')
    f.write('\n}  // namespace key\n\n'
            '}  // namespace policy\n\n'
            '#endif  // CHROME_COMMON_POLICY_CONSTANTS_H_\n')


#------------------ policy constants source ------------------------#
def _WritePolicyConstantSource(template_file_contents, args, opts):
  platform = args[0];
  with open(opts.source_path, "w") as f:
    _OutputGeneratedWarningForC(f, args[1])
    f.write('#include "policy/policy_constants.h"\n'
            '\n'
            'namespace policy {\n'
            '\n')
    if platform == "win":
      f.write('#if defined(GOOGLE_CHROME_BUILD)\n'
              'const wchar_t kRegistrySubKey[] = '
              'L"' + CHROME_SUBKEY + '";\n'
              '#else\n'
              'const wchar_t kRegistrySubKey[] = '
              'L"' + CHROMIUM_SUBKEY + '";\n'
              '#endif\n\n')
    f.write('namespace key {\n\n')
    for policy_name in _GetPolicyNameList(template_file_contents):
      f.write('const char k%s[] = "%s";\n' % (policy_name, policy_name))
    f.write('\n}  // namespace key\n\n'
            '}  // namespace policy\n')


#------------------ policy type enumeration header -----------------#
def _WritePolicyTypeEnumerationHeader(template_file_contents, args, opts):
  with open(opts.type_path, "w") as f:
    _OutputGeneratedWarningForC(f, args[1])
    f.write('#ifndef CHROME_BROWSER_POLICY_CONFIGURATION_POLICY_TYPE_H_\n'
            '#define CHROME_BROWSER_POLICY_CONFIGURATION_POLICY_TYPE_H_\n'
            '#pragma once\n'
            '\n'
            'namespace policy {\n'
            '\n'
            'enum ConfigurationPolicyType {\n')
    for policy_name in _GetPolicyNameList(template_file_contents):
      f.write('  kPolicy' + policy_name + ",\n");
    f.write('};\n\n'
            '}  // namespace policy\n\n'
            '#endif  // CHROME_BROWSER_POLICY_CONFIGURATION_POLICY_TYPE_H_\n')


#------------------ policy protobuf --------------------------------#
PROTO_HEAD = '''
syntax = "proto2";

option optimize_for = LITE_RUNTIME;

package enterprise_management;

message StringList {
  repeated string entries = 1;
}

message PolicyOptions {
  enum PolicyMode {
    // The given settings are applied regardless of user choice.
    MANDATORY = 0;
    // The user may choose to override the given settings.
    RECOMMENDED = 1;
  }
  optional PolicyMode mode = 1 [default = MANDATORY];
}

'''


PROTOBUF_TYPE = {
  'main': 'bool',
  'string': 'string',
  'string-enum': 'string',
  'int': 'int64',
  'int-enum': 'int64',
  'list': 'StringList',
}


# Field IDs [1..RESERVED_IDS] will not be used in the wrapping protobuf.
RESERVED_IDS = 2


def _WritePolicyProto(file, policy, fields):
  file.write('message %sProto {\n' % policy['name'])
  file.write('  optional PolicyOptions policy_options = 1;\n')
  file.write('  optional %s %s = 2;\n' %
             (PROTOBUF_TYPE[policy['type']], policy['name']))
  file.write('}\n\n')
  fields += ['  optional %sProto %s = %s;\n' %
             (policy['name'], policy['name'], policy['id'] + RESERVED_IDS)]


def _WriteProtobuf(template_file_contents, args, outfilepath):
  with open(outfilepath, 'w') as f:
    _OutputGeneratedWarningForC(f, args[1])
    f.write(PROTO_HEAD)

    fields = []
    f.write('// PBs for individual settings.\n\n')
    for policy in template_file_contents['policy_definitions']:
      if policy['type'] == 'group':
        for sub_policy in policy['policies']:
          _WritePolicyProto(f, sub_policy, fields)
      else:
        _WritePolicyProto(f, policy, fields)

    f.write('// --------------------------------------------------\n'
            '// Big wrapper PB containing the above groups.\n\n'
            'message CloudPolicySettings {\n')
    f.write(''.join(fields))
    f.write('}\n\n')


#------------------ protobuf decoder -------------------------------#
CPP_HEAD = '''
#include <limits>
#include <map>
#include <string>

#include "base/logging.h"
#include "base/values.h"
#include "chrome/browser/policy/configuration_policy_provider.h"
#include "chrome/browser/policy/policy_map.h"
#include "chrome/browser/policy/proto/device_management_backend.pb.h"
#include "policy/configuration_policy_type.h"

using google::protobuf::RepeatedPtrField;

namespace policy {

namespace em = enterprise_management;

Value* DecodeIntegerValue(google::protobuf::int64 value) {
  if (value < std::numeric_limits<int>::min() ||
      value > std::numeric_limits<int>::max()) {
    LOG(WARNING) << "Integer value " << value
                 << " out of numeric limits, ignoring.";
    return NULL;
  }

  return Value::CreateIntegerValue(static_cast<int>(value));
}

ListValue* DecodeStringList(const em::StringList& string_list) {
  ListValue* list_value = new ListValue;
  RepeatedPtrField<std::string>::const_iterator entry;
  for (entry = string_list.entries().begin();
       entry != string_list.entries().end(); ++entry) {
    list_value->Append(Value::CreateStringValue(*entry));
  }
  return list_value;
}

void DecodePolicy(const em::CloudPolicySettings& policy,
                  PolicyMap* mandatory, PolicyMap* recommended) {
  DCHECK(mandatory);
  DCHECK(recommended);
'''


CPP_FOOT = '''}

}  // namespace policy
'''


def _CreateValue(type):
  if type == 'main':
    return "Value::CreateBooleanValue"
  elif type in ('int', 'int-enum'):
    return "DecodeIntegerValue"
  elif type in ('string', 'string-enum'):
    return "Value::CreateStringValue"
  elif type == 'list':
    return "DecodeStringList"
  else:
    raise NotImplementedError()


def _WritePolicyCode(file, policy):
  membername = policy['name'].lower()
  proto_type = "%sProto" % policy['name']
  proto_name = "%s_proto" % membername
  file.write('  if (policy.has_%s()) {\n' % membername)
  file.write('    const em::%s& %s = policy.%s();\n' %
             (proto_type, proto_name, membername))
  file.write('    if (%s.has_%s()) {\n' % (proto_name, membername))
  file.write('      Value* value = %s(%s.%s());\n' %
             (_CreateValue(policy['type']), proto_name, membername))
  file.write('      PolicyMap* destination = mandatory;\n'
             '      if (%s.has_policy_options()) {\n'
             '        switch(%s.policy_options().mode()) {\n' %
              (proto_name, proto_name))
  file.write('          case em::PolicyOptions::RECOMMENDED:\n'
             '            destination = recommended;\n'
             '            break;\n'
             '          case em::PolicyOptions::MANDATORY:\n'
             '            break;\n'
             '        }\n'
             '      }\n'
             '      destination->Set(kPolicy%s, value);\n' %
              policy['name'])
  file.write('    }\n'
             '  }\n')


def _WriteProtobufParser(template_file_contents, args, outfilepath):
  with open(outfilepath, 'w') as f:
    _OutputGeneratedWarningForC(f, args[1])
    f.write(CPP_HEAD)
    for policy in template_file_contents['policy_definitions']:
      if policy['type'] == 'group':
        for sub_policy in policy['policies']:
          _WritePolicyCode(f, sub_policy)
      else:
        _WritePolicyCode(f, policy)
    f.write(CPP_FOOT)


#------------------ main() -----------------------------------------#
if __name__ == '__main__':
  main();
