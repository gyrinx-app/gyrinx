import pytest
from gyrinx.models import format_cost_display
from gyrinx.content.models import ContentEquipmentUpgrade, ContentWeaponAccessory


class TestFormatCostDisplay:
    """Test the format_cost_display function."""
    
    def test_positive_cost_without_sign(self):
        """Test positive cost without sign."""
        assert format_cost_display(5) == "5¢"
        assert format_cost_display(100) == "100¢"
        
    def test_positive_cost_with_sign(self):
        """Test positive cost with sign."""
        assert format_cost_display(5, show_sign=True) == "+5¢"
        assert format_cost_display(100, show_sign=True) == "+100¢"
        
    def test_negative_cost_without_sign(self):
        """Test negative cost without sign."""
        assert format_cost_display(-5) == "-5¢"
        assert format_cost_display(-100) == "-100¢"
        
    def test_negative_cost_with_sign(self):
        """Test negative cost with sign - should not add extra + sign."""
        assert format_cost_display(-5, show_sign=True) == "-5¢"
        assert format_cost_display(-100, show_sign=True) == "-100¢"
        
    def test_zero_cost(self):
        """Test zero cost."""
        assert format_cost_display(0) == "0¢"
        assert format_cost_display(0, show_sign=True) == "0¢"
        
    def test_string_input(self):
        """Test string input that can be converted to int."""
        assert format_cost_display("5") == "5¢"
        assert format_cost_display("5", show_sign=True) == "+5¢"
        assert format_cost_display("-5") == "-5¢"
        
    def test_non_numeric_string(self):
        """Test non-numeric string returns as-is."""
        assert format_cost_display("2D6X10") == "2D6X10"
        assert format_cost_display("not_a_number") == "not_a_number"


@pytest.mark.django_db
class TestModelCostDisplay:
    """Test cost_display methods on models."""
    
    def test_equipment_upgrade_negative_cost_display(self):
        """Test that ContentEquipmentUpgrade with negative cost displays correctly."""
        upgrade = ContentEquipmentUpgrade(
            name="Discount Upgrade",
            cost=-10,
            position=0
        )
        assert upgrade.cost_display() == "-10¢"
        
    def test_weapon_accessory_negative_cost_display(self):
        """Test that ContentWeaponAccessory with negative cost displays correctly."""
        accessory = ContentWeaponAccessory(
            name="Discount Accessory",
            cost=-5
        )
        assert accessory.cost_display() == "-5¢"


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])