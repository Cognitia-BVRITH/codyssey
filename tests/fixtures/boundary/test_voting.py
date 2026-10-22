from voting import can_vote


def test_at_voting_age():
    assert can_vote(18) is True


def test_below_voting_age():
    assert can_vote(17) is False


def test_above_voting_age():
    assert can_vote(19) is True
