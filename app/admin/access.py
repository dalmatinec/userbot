from dataclasses import dataclass, field


@dataclass
class Access:
    env: frozenset[int]
    extra: set[int] = field(default_factory=set)

    def allowed(self, user_id: int) -> bool:
        return user_id in self.env or user_id in self.extra

    @property
    def all(self) -> set[int]:
        return set(self.env) | self.extra
