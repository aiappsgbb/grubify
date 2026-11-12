namespace GrubifyApi.Models
{
    public class Deal
    {
        public int Id { get; set; }
        public string Headline { get; set; } = string.Empty;
        public int DiscountPercent { get; set; }
        public decimal DealPrice { get; set; }
        public DateTime ExpiresAt { get; set; }
        public FoodItem FoodItem { get; set; } = new();
    }
}
