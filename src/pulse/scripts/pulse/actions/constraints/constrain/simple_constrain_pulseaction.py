
import pymel.core as pm

import pulse
import pulse.nodes


class SimpleConstrainAction(pulse.BuildAction):

    def validate(self):
        if not self.leader:
            raise pulse.BuildActionError("leader must be set")
        if not self.follower:
            raise pulse.BuildActionError("follower must be set")

    def run(self):

        shouldCreateOffset = False
        if self.createFollowerOffset == 0:
            # Always
            shouldCreateOffset = True
        elif self.createFollowerOffset == 1 and self.follower.nodeType() != 'joint':
            # Exclude Joints and the follower is not a joint
            shouldCreateOffset = True

        _follower = self.follower
        if shouldCreateOffset:
            _follower = pm.group(p=self.follower.getParent(), name='{0}_offset'.format(self.follower))
            _follower.t.set(self.follower.t.get())
            _follower.r.set(self.follower.r.get())
            _follower.s.set(self.follower.s.get())
            self.follower.setParent(_follower)

        # parent constrain (translate and rotate)
        pc = pm.parentConstraint(self.leader, _follower, mo=True)
        # set interpolation mode to Shortest
        pc.interpType.set(2)

        # scale constrain
        sc = pm.scaleConstraint(self.leader, _follower, mo=True)
        if self.worldSpaceScaling:
            pulse.nodes.makeScaleConstraintWorldSpace(sc)

        # lockup the constraints
        pulse.nodes.setConstraintLocked(pc, True)
        pulse.nodes.setConstraintLocked(sc, True)
