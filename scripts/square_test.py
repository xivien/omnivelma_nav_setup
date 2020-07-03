#!/usr/bin/env python

import rospy
import math as m
from geometry_msgs.msg import Pose, Twist, Vector3, Pose2D
from nav_msgs.msg import Odometry, Path
from tf.transformations import euler_from_quaternion, quaternion_from_euler
from numpy import sign
import rosbag
import sys
import tf


class square_test:
    def __init__(self, mode=1, bag_name='square_test.bag'):
        self.bag = rosbag.Bag(bag_name, 'w')
        self.mode = mode
        self.tol = 1e-1
        self.path_subscriber = rospy.Subscriber(
            "/path", Path, self.callback_set_vel)
        self.odom_subscriber = rospy.Subscriber(
            "/odom/filtered", Odometry, self.callback_read_odom)
        self.pub = rospy.Publisher("/cmd_vel", Twist, queue_size=10)
        self.listener = tf.TransformListener()

        # needed so ros has time to get self.current_x for two publishers
        rospy.sleep(1)
        self.error_pub = rospy.Publisher("/error", Pose2D, queue_size=10)
        self.gazebo_odom_subscriber = rospy.Subscriber(
            "/PoseGlob", Odometry, self.callback_read_gazebo_odom)

        self.freq = 20
        self.rate = rospy.Rate(self.freq)  # 20hz

    def callback_read_odom(self, msg):
        self.current_x = msg.pose.pose.position.x
        self.current_y = msg.pose.pose.position.y
        orient = msg.pose.pose.orientation
        _, _, self.current_theta = euler_from_quaternion(
            [orient.x, orient.y, orient.z, orient.w])

    def callback_read_gazebo_odom(self, msg):
        self.ideal_x = msg.pose.pose.position.x
        self.ideal_y = msg.pose.pose.position.y
        ideal_orient = msg.pose.pose.orientation
        _, _, self.ideal_theta = euler_from_quaternion(
            [ideal_orient.x, ideal_orient.y, ideal_orient.z, ideal_orient.w])

        error = Pose2D()
        error.x = self.current_x - self.ideal_x
        error.y = self.current_y - self.ideal_y
        last_theta = error.theta
        error.theta = self.current_theta - self.ideal_theta
        if(abs(error.theta) > 1):
            error.theta = last_theta
        self.error_pub.publish(error)
        (trans, rot) = self.listener.lookupTransform(
            '/map', '/base_footprint', rospy.Time(0))
        _, _, glob_theta = euler_from_quaternion(rot)
        try:

            #    writing to a bag file
            self.bag.write('/gazebo_odom', Pose2D(self.ideal_x,
                                                  self.ideal_y, self.ideal_theta))
            # self.bag.write('/odometry', Pose2D(self.current_x,
            #                                    self.current_y, self.current_theta))
            self.bag.write('/odometry', Pose2D(trans[0], trans[1], glob_theta))

            self.bag.write('/error', error)
        except:
            self.rate.sleep()
            self.bag.close()
            print("bag closed")

    def callback_set_vel(self, msg):
        self.new_msg = Twist()

        self.omega = 0.5
        self.vel = 0.5

        self.path = msg.poses
        self.stop_msg = Twist()
        if self.mode == 1:
            self.mode_1()
        elif self.mode == 2:
            self.mode_2()

        self.pub.publish(self.new_msg)
        self.rate.sleep()
        rospy.sleep(1.)
        # self.bag.close()
        # rospy.signal_shutdown("a")

    def get_vel_sign(self, direct, omega):

        if direct < 0 and direct > -m.pi:
            z = -omega

        elif direct < -m.pi and direct > -2*m.pi:
            z = omega

        elif direct > 0 and direct < m.pi:
            z = omega

        elif direct > m.pi and direct < 2*m.pi:
            z = -omega

        else:
            z = omega

        return z

    def mode_1(self):
        for dest in self.path:

            last_direct = 1000000
            last_dist = 100000

            x = dest.pose.position.x
            y = dest.pose.position.y

            dx = x - self.ideal_x
            dy = y - self.ideal_y

            direct = m.atan2(dy, dx) - self.ideal_theta

            last_direct = direct

            while True:

                self.new_msg.angular.z = self.get_vel_sign(direct, self.omega)

                self.pub.publish(self.new_msg)
                self.rate.sleep()

                last_direct = direct

                direct = m.atan2(dy, dx) - self.ideal_theta

                # cast to (-pi:pi) range
                if direct < -m.pi:
                    direct += 2*m.pi
                elif direct > m.pi:
                    direct -= 2*m.pi

                if (abs(direct) < 0.1) and (abs(direct) > abs(last_direct)):
                    break

            self.new_msg.angular.z = 0

            dx = x - self.ideal_x
            dy = y - self.ideal_y
            dist = m.sqrt(dx*dx + dy*dy)
            while (abs(dist) <= abs(last_dist) or dist > self.tol):

                self.new_msg.linear.x = self.vel
                self.pub.publish(self.new_msg)
                self.rate.sleep()

                last_dist = dist

                dx = x - self.ideal_x
                dy = y - self.ideal_y

                dist = m.sqrt(dx*dx + dy*dy)

            self.new_msg.linear.x = 0

        last_direct = 1000000
        direct = - self.ideal_theta

        # turn to starting pose
        while True:
            self.new_msg.angular.z = self.get_vel_sign(direct, self.omega)

            self.pub.publish(self.new_msg)
            self.rate.sleep()

            last_direct = direct

            direct = -self.ideal_theta

            # cast to (-pi:pi) range
            if direct < -m.pi:
                direct += 2*m.pi
            elif direct > m.pi:
                direct -= 2*m.pi

            if (abs(direct) < 0.1) and (abs(direct) > abs(last_direct)):
                break

        self.new_msg.angular.z = 0

    def mode_2(self):
        for dest in self.path:
            last_dx = 100000
            last_dy = 100000

            x = dest.pose.position.x
            y = dest.pose.position.y

            dx = x - self.ideal_x
            dy = y - self.ideal_y

            while ((abs(dx) <= abs(last_dx) and abs(dy) <= abs(last_dy)) or abs(dx) >= self.tol or abs(dy) >= self.tol):

                self.new_msg.linear.x = self.vel*dx/(abs(dx)+abs(dy))
                self.new_msg.linear.y = self.vel*dy/(abs(dx)+abs(dy))
                self.pub.publish(self.new_msg)
                self.rate.sleep()

                last_dx = dx
                last_dy = dy

                dx = x - self.ideal_x
                dy = y - self.ideal_y

        self.new_msg.linear.x = 0
        self.new_msg.linear.y = 0


if __name__ == '__main__':
    rospy.init_node('Square_test',  disable_signals=True)
    square_test(1, "square_test_EKFamcl_rot.bag")
    rospy.spin()
