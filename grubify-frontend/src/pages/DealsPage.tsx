import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  CardMedia,
  Chip,
  CircularProgress,
  Snackbar,
  Typography,
} from '@mui/material';
import {
  LocalFireDepartment as HotDealsIcon,
  AccessTime as TimeIcon,
} from '@mui/icons-material';
import { Deal } from '../types';
import { cartService, dealService } from '../services/api';

const REFRESH_INTERVAL_MS = 3000;

const formatTimeLeft = (expiresAt: string): string => {
  const msLeft = Math.max(0, new Date(expiresAt).getTime() - Date.now());
  const minutes = Math.floor(msLeft / 60000);
  const seconds = Math.floor((msLeft % 60000) / 1000);
  return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
};

const DealsPage: React.FC = () => {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [addedMessage, setAddedMessage] = useState<string | null>(null);

  const loadDeals = useCallback(async () => {
    try {
      const data = await dealService.getHotDeals();
      setDeals(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error('Error loading hot deals:', err);
      setError("We couldn't refresh today's hot deals. We'll keep trying.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDeals();
    // Live deals feed: prices and countdowns refresh continuously while the page is open
    const interval = setInterval(loadDeals, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadDeals]);

  const handleAddToCart = async (deal: Deal) => {
    try {
      await cartService.addItem('user123', {
        foodItemId: deal.foodItem.id,
        quantity: 1,
        specialInstructions: `Hot Deal: ${deal.headline}`,
      });
      setAddedMessage(`${deal.foodItem.name} added to cart`);
    } catch (err) {
      console.error('Error adding deal to cart:', err);
      setError('Unable to add this deal to your cart. Please try again.');
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ mb: 4, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <HotDealsIcon color="primary" sx={{ fontSize: 40 }} />
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h4" component="h1" fontWeight="bold">
            Hot Deals
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Limited-time offers from your favorite restaurants, updated live.
          </Typography>
        </Box>
        {lastUpdated && (
          <Chip
            color={error ? 'default' : 'secondary'}
            variant="outlined"
            label={`Updated ${lastUpdated.toLocaleTimeString()}`}
          />
        )}
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: {
            xs: '1fr',
            sm: 'repeat(2, 1fr)',
            md: 'repeat(3, 1fr)',
          },
          gap: 3,
        }}
      >
        {deals.map((deal) => (
          <Card key={deal.id} sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Box sx={{ position: 'relative' }}>
              <CardMedia
                component="img"
                height="200"
                image={deal.foodItem.imageUrl}
                alt={deal.foodItem.name}
                sx={{ objectFit: 'cover' }}
              />
              <Chip
                label={`${deal.discountPercent}% OFF`}
                color="primary"
                sx={{ position: 'absolute', top: 12, left: 12, fontWeight: 'bold' }}
              />
            </Box>
            <CardContent sx={{ flexGrow: 1 }}>
              <Typography variant="overline" color="primary" fontWeight="bold">
                {deal.headline}
              </Typography>
              <Typography variant="h6" component="h2" gutterBottom>
                {deal.foodItem.name}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {deal.foodItem.description}
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mb: 1 }}>
                <Typography variant="h5" color="primary" fontWeight="bold">
                  ${deal.dealPrice.toFixed(2)}
                </Typography>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ textDecoration: 'line-through' }}
                >
                  ${deal.foodItem.price.toFixed(2)}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <TimeIcon sx={{ fontSize: 16, mr: 0.5, color: 'text.secondary' }} />
                <Typography variant="body2" color="text.secondary">
                  Ends in {formatTimeLeft(deal.expiresAt)}
                </Typography>
              </Box>
            </CardContent>
            <CardActions sx={{ p: 2, pt: 0 }}>
              <Button fullWidth variant="contained" onClick={() => handleAddToCart(deal)}>
                Add to Cart
              </Button>
            </CardActions>
          </Card>
        ))}
      </Box>

      {deals.length === 0 && !error && (
        <Box textAlign="center" py={8}>
          <Typography variant="h6" color="text.secondary">
            No hot deals right now. Check back soon!
          </Typography>
        </Box>
      )}

      <Snackbar
        open={addedMessage !== null}
        autoHideDuration={3000}
        onClose={() => setAddedMessage(null)}
        message={addedMessage}
      />
    </Box>
  );
};

export default DealsPage;
