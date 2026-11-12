using System.Collections.Concurrent;
using Microsoft.AspNetCore.Mvc;
using GrubifyApi.Models;

namespace GrubifyApi.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class DealsController : ControllerBase
    {
        // Full HD RGBA promo banner rendered for each deal
        private const int BannerWidth = 1920;
        private const int BannerHeight = 1080;
        private const int BytesPerPixel = 4;
        private const int RowSizeBytes = BannerWidth * BytesPerPixel;
        private const int BannerSizeBytes = RowSizeBytes * BannerHeight;

        private static readonly (int FoodItemId, int DiscountPercent, string Headline)[] HotDeals =
        {
            (1, 30, "Pizza Night Special"),
            (5, 25, "Sushi Happy Hour"),
            (7, 20, "Curry Craving Combo"),
            (10, 35, "Burger Blowout"),
            (13, 15, "Healthy Bowl Deal"),
            (14, 40, "Smoothie Flash Sale"),
        };

        // Rendered promo banners are cached so the live Hot Deals feed stays fast
        private static readonly ConcurrentDictionary<string, List<byte[]>> PromoBannerCache = new();

        [HttpGet]
        public ActionResult<IEnumerable<Deal>> GetHotDeals()
        {
            var now = DateTime.UtcNow;
            var expiresAt = new DateTime(now.Year, now.Month, now.Day, now.Hour, 0, 0, DateTimeKind.Utc).AddHours(1);
            var deals = new List<Deal>();

            foreach (var (foodItemId, discountPercent, headline) in HotDeals)
            {
                var foodItem = FoodItemsController.FoodItems.First(f => f.Id == foodItemId);
                var cacheKey = $"deal-{foodItemId}-{now.Ticks}";
                var banner = PromoBannerCache.GetOrAdd(cacheKey, _ => new List<byte[]>(BannerHeight));
                RenderPromoBanner(banner, foodItemId, discountPercent);

                deals.Add(new Deal
                {
                    Id = foodItemId,
                    Headline = headline,
                    DiscountPercent = discountPercent,
                    DealPrice = Math.Round(foodItem.Price * (100 - discountPercent) / 100m, 2),
                    ExpiresAt = expiresAt,
                    FoodItem = foodItem
                });
            }

            Console.WriteLine($"Hot deals served. Promo banner cache: {PromoBannerCache.Count} banners, {(long)PromoBannerCache.Count * BannerSizeBytes / (1024 * 1024)}MB");
            return Ok(deals);
        }

        // Streams the banner into the cache one scanline at a time
        private static void RenderPromoBanner(List<byte[]> banner, int foodItemId, int discountPercent)
        {
            var fill = (byte)(foodItemId * 31 + discountPercent);
            for (var y = 0; y < BannerHeight; y++)
            {
                var row = new byte[RowSizeBytes];
                row.AsSpan().Fill(fill);
                banner.Add(row);
            }
        }
    }
}
