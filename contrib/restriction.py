
# # def is_restricted(self, asset, dt):
# #     if isinstance(asset, Asset):
# #         return any(
# #             r.is_restricted(asset, dt) for r in self.sub_restrictions
# #         )
# #
# #     return reduce(
# #         operator.or_,
# #         (r.is_restricted(asset, dt) for r in self.sub_restrictions)
# #     )
