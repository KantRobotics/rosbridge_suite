# Software License Agreement (BSD License)
#
# Copyright (c) 2012, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from threading import Thread

import rclpy
from rclpy.action import ActionClient

from rclpy.expand_topic_name import expand_topic_name
from rosbridge_library.internal.message_conversion import (
    extract_values,
    populate_instance,
)
from rosbridge_library.internal.ros_loader import (
    get_action_class,
    get_action_request_instance,
)


class InvalidActionException(Exception):
    def __init__(self, actionname):
        Exception.__init__(self, "Action %s does not exist" % actionname)


class ActionCaller(Thread):
    def __init__(self, action, args, success_callback, error_callback, node_handle):
        """Create a action caller for the specified action.  Use start()
        to start in a separate thread or run() to run in this thread.

        Keyword arguments:
        action           -- the name of the action to call
        args             -- arguments to pass to the action.  Can be an
        ordered list, or a dict of name-value pairs.  Anything else will be
        treated as though no arguments were provided (which is still valid for
        some kinds of action)
        success_callback -- a callback to call with the JSON result of the
        action call
        error_callback   -- a callback to call if an error occurs.  The
        callback will be passed the exception that caused the failure
        node_handle      -- a ROS2 node handle to call actions.
        """
        Thread.__init__(self)
        self.daemon = True
        self.action = action
        self.args = args
        self.success = success_callback
        self.error = error_callback
        self.node_handle = node_handle

    def run(self):
        try:
            # Call the action and pass the result to the success handler
            self.success(call_action(self.node_handle, self.action, self.args))
        except Exception as e:
            # On error, just pass the exception to the error handler
            self.error(e)


def args_to_action_request_instance(action, inst, args):
    """Populate a action request instance with the provided args

    args can be a dictionary of values, or a list, or None

    Propagates any exceptions that may be raised."""
    msg = {}
    if isinstance(args, list):
        msg = dict(zip(inst.get_fields_and_field_types().keys(), args))
    elif isinstance(args, dict):
        msg = args

    # Populate the provided instance, propagating any exceptions
    populate_instance(msg, inst)


def call_action(node_handle, action, args=None):
    # Given the action name, fetch the type and class of the action,
    # and a request instance

    # This should be equivalent to rospy.resolve_name.
    action = expand_topic_name(action, node_handle.get_name(), node_handle.get_namespace())

    action_names_and_types = dict(rclpy.action.get_action_names_and_types(node_handle))
    action_type = action_names_and_types.get(action)
    if action_type is None:
        raise InvalidActionException(action)
    # action_type is a tuple of types at this point; only one type is supported.
    if len(action_type) > 1:
        node_handle.get_logger().warning(f"More than one action type detected: {action_type}")
    action_type = action_type[0]

    action_class = get_action_class(action_type)
    inst = get_action_request_instance(action_type)

    # Populate the instance with the provided args
    args_to_action_request_instance(action, inst, args)

    client = ActionClient(node_handle, action_class, action)

    result = client.send_goal(inst)
    if result is not None:
        # Turn the response into JSON and pass to the callback
        json_response = extract_values(result)
    else:
        raise Exception(result)

    return json_response