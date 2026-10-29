from scripts.audit_refinement_release import contains_credential_pattern


def test_public_openssh_protocol_algorithm_does_not_masquerade_as_gateway_key():
    assert not contains_credential_pattern(b'\x00sk-ecdsa-sha2-nistp256-cert-v01@openssh.com\x00')


def test_similar_prefix_without_exact_protocol_suffix_remains_a_detection():
    assert contains_credential_pattern(b'sk-'+b'ecdsa-sha2-nistp256-cert-v01-extra-value')
    assert contains_credential_pattern(b'sk-'+b'fixture-value-for-release-scanner'*2)


def test_protocol_identifier_does_not_exempt_an_adjacent_credential():
    assert contains_credential_pattern(b'sk-ecdsa-sha2-nistp256-cert-v01@openssh.com\x00sk-'+b'fixture-only-value'*3)
