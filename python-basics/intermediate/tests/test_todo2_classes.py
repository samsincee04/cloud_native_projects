from src.todo2_classes import Logger, Service
def test_logger_stores_messages():
    logger = Logger()
    logger.log("hello")
    logger.log("world")
    assert logger.messages() == ["hello", "world"]

def test_service_uses_composition_and_logs():
    logger = Logger()
    svc = Service(name="alpha", factor=3, logger=logger)
    
    out = svc.handle(10)
    assert out == 30
    
    
    msgs = logger.messages()
    assert len(msgs) == 1
    # Must include key details (flexible format)
    assert "alpha" in msgs[0]
    assert "10" in msgs[0]
    assert "3" in msgs[0]
    assert "30" in msgs[0]

def test_service_str():
    logger = Logger()
    svc = Service(name="beta", factor=2, logger=logger)
    s = str(svc)
    assert "Service" in s
    assert "beta" in s
    assert "2" in s